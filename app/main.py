import asyncio
import logging
import os
from collections import OrderedDict
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import init_db, get_session
from app.models import Warga, SuratPermohonan, ChatSession
from app.conversation import process_message
from app.pdf_generator import generate_pdf, _generate_nomor_surat
from app.wa_client import wa_client
from app.langchain_agent import ask_rag

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

MAX_DEDUP_CACHE = 500
_processed_msg_ids: OrderedDict[str, bool] = OrderedDict()

MAX_PHONE_LOCKS = 200
_phone_locks: OrderedDict[str, asyncio.Lock] = OrderedDict()


def _get_phone_lock(phone: str) -> asyncio.Lock:
    if phone not in _phone_locks:
        _phone_locks[phone] = asyncio.Lock()
        if len(_phone_locks) > MAX_PHONE_LOCKS:
            _phone_locks.popitem(last=False)
    return _phone_locks[phone]


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    os.makedirs("output", exist_ok=True)
    os.makedirs("data", exist_ok=True)

    if settings.GEMINI_API_KEY:
        try:
            from app.rag_store import build_vectorstore
            build_vectorstore()
            logger.info("RAG vectorstore initialized")
        except Exception as e:
            logger.warning(f"RAG vectorstore init failed (non-fatal): {e}")

    logger.info("Chatbot Administrasi Desa started")
    yield
    logger.info("Chatbot Administrasi Desa stopped")


app = FastAPI(
    title="Chatbot Administrasi Desa",
    description="Webhook server untuk chatbot layanan administrasi desa via WhatsApp",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "chatbot-administrasi-desa"}


@app.post("/webhook")
async def webhook_handler(request: Request, session: AsyncSession = Depends(get_session)):
    """
    Menerima webhook dari WA API (Baileys-based).
    Format incoming:
    {
        "event": "message.received",
        "data": {
            "phone_number": "628123456789",
            "content": "halo",
            "contact_name": "Budi",
            "type": "text",
            "direction": "INCOMING"
        }
    }
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    event = body.get("event", "")
    if event != "message.received":
        return JSONResponse(content={"status": "ignored", "reason": "not a message event"})

    data = body.get("data", {})
    direction = data.get("direction", "")
    msg_type = data.get("type", "")
    msg_id = data.get("id", "")

    if direction != "INCOMING":
        return JSONResponse(content={"status": "ignored", "reason": "not incoming"})

    if msg_id:
        if msg_id in _processed_msg_ids:
            logger.info(f"Duplicate message ignored: {msg_id}")
            return JSONResponse(content={"status": "ignored", "reason": "duplicate"})
        _processed_msg_ids[msg_id] = True
        if len(_processed_msg_ids) > MAX_DEDUP_CACHE:
            _processed_msg_ids.popitem(last=False)

    phone = data.get("phone_number") or ""
    # Fallback: extract from 'from'/'sender_jid' when phone_number is null
    # Handles @s.whatsapp.net (extract number) and @lid (keep full JID for API routing)
    if not phone:
        from_jid = data.get("from") or data.get("sender_jid") or ""
        if "@s.whatsapp.net" in from_jid:
            phone = from_jid.split("@")[0]
        elif from_jid:
            phone = from_jid  # Keep full JID e.g. "77864099643580@lid"
    contact_name = data.get("contact_name", "")

    if msg_type == "button_response":
        content = data.get("button_id", data.get("content", "")).strip()
    elif msg_type == "list_response":
        content = data.get("row_id", data.get("content", "")).strip()
    elif msg_type == "text":
        content = data.get("content", "").strip()
    else:
        if phone:
            await wa_client.send_text(
                phone,
                "Maaf, saat ini saya hanya bisa memproses pesan teks. Silakan kirim pesan dalam bentuk teks."
            )
        return JSONResponse(content={"status": "ignored", "reason": "unsupported message type"})

    if not phone or not content:
        return JSONResponse(status_code=400, content={"error": "Missing phone or content"})

    # Block group chats: format groupId-timestamp or group JID starting with 120363
    if "-" in phone or phone.startswith("120363") or len(phone) > 20:
        logger.info(f"Non-personal chat ignored: {phone}")
        return JSONResponse(content={"status": "ignored", "reason": "non-personal chat"})

    logger.info(f"Pesan masuk dari {phone} ({contact_name}): {content}")

    lock = _get_phone_lock(phone)
    async with lock:
        try:
            result = await process_message(session, phone, content, contact_name)

            reply = result["reply"]
            action = result["action"]

            if action == "check_riwayat":
                await _handle_riwayat(session, phone)
            elif action == "ask_rag":
                await _handle_rag_question(phone, result["data"])
            elif action == "send_list_menu":
                await _handle_send_list_menu(phone, reply, result["data"])
            elif action == "send_confirm_buttons":
                await _handle_send_confirm_buttons(phone, reply, result["data"])
            elif action == "send_qris":
                await _handle_send_qris(phone, reply, result["data"])
            else:
                if reply:
                    await wa_client.send_text(phone, reply)

                if action == "generate_surat":
                    try:
                        await _handle_generate_surat(session, result["data"])
                    except Exception as e:
                        logger.error(f"Error generate surat: {e}", exc_info=True)
                        await wa_client.send_text(
                            phone,
                            "Maaf, terjadi kesalahan saat membuat surat. Silakan coba lagi dengan mengetik *halo*."
                        )
        except Exception as e:
            logger.error(f"Error processing message from {phone}: {e}", exc_info=True)
            try:
                await wa_client.send_text(phone, "Maaf, terjadi kesalahan. Silakan coba lagi dengan mengetik *halo*.")
            except Exception:
                pass

    return JSONResponse(content={"status": "ok"})


async def _handle_send_list_menu(phone: str, fallback_text: str, data: dict):
    # NOTE: send_list/send_buttons tidak di-render oleh Baileys (unofficial API).
    # Kirim fallback text sebagai primary UX. Interactive endpoints tetap tersedia
    # di wa_client.py untuk migrasi ke Meta Cloud API di masa depan.
    await wa_client.send_text(phone, fallback_text)


async def _handle_send_confirm_buttons(phone: str, fallback_text: str, data: dict):
    # NOTE: Sama seperti di atas — Baileys tidak render buttons.
    # Fallback text sudah didesain dengan angka 1/2/3 yang mudah dipakai.
    await wa_client.send_text(phone, fallback_text)


async def _handle_send_qris(phone: str, text: str, data: dict):
    """Send QRIS payment: text summary → QR image → fallback Snap link."""
    if text:
        await wa_client.send_text(phone, text)
    qr_url = data.get("qr_url", "")
    redirect_url = data.get("redirect_url", "")
    order_id = data.get("order_id", "")

    if qr_url:
        await asyncio.sleep(5)
        result = await wa_client.send_image(phone, qr_url, caption=f"QRIS — {order_id}\nScan dari m-banking atau e-wallet manapun")
        if "error" in result:
            logger.error(f"Failed to send QRIS image to {phone}: {result}")
            # Fallback: send QR URL as text
            await asyncio.sleep(2)
            fallback = f"⚠️ Gagal mengirim gambar QR.\n\nLink QR Code:\n{qr_url}"
            if redirect_url:
                fallback += f"\n\nAtau bayar via halaman ini:\n{redirect_url}"
            await wa_client.send_text(phone, fallback)
        elif redirect_url:
            # QR sent successfully — also send Snap link as alternative
            await asyncio.sleep(3)
            await wa_client.send_text(
                phone,
                f"Atau bisa juga bayar via link berikut (pilih metode lain seperti Transfer Bank):\n{redirect_url}"
            )
    else:
        if redirect_url:
            await wa_client.send_text(phone, f"Bayar melalui link berikut:\n{redirect_url}")
        else:
            await wa_client.send_text(phone, "⚠️ QR Code tidak tersedia. Silakan ketik *iuran* untuk mengulang.")


async def _handle_rag_question(phone: str, data: dict):
    question = data.get("question", "")
    if not question:
        await wa_client.send_text(phone, "Silakan ketik pertanyaan Anda tentang desa, atau ketik *menu* untuk membuat surat.")
        return

    _RAG_FOOTERS = [
        "\n\n---\n💡 Ketik *menu* untuk membuat surat, atau lanjut bertanya.",
        "\n\n---\nAda pertanyaan lain? Silakan ketik langsung. Ketik *menu* untuk layanan surat.",
        "\n\n---\nSemoga membantu! Ketik *menu* jika perlu membuat surat.",
        "\n\n---\nMasih ada yang ingin ditanyakan? Atau ketik *menu* untuk membuat surat.",
        "\n\n---\nJangan ragu bertanya lagi. Ketik *menu* kapan saja untuk layanan surat.",
    ]

    try:
        import random
        answer = await ask_rag(phone, question)
        footer = random.choice(_RAG_FOOTERS)
        await wa_client.send_text(phone, answer + footer)
    except Exception as e:
        logger.error(f"RAG error for {phone}: {e}", exc_info=True)
        await wa_client.send_text(phone, "Maaf, terjadi kesalahan saat mencari informasi. Silakan coba lagi atau ketik *menu* untuk membuat surat.")


async def _handle_riwayat(session: AsyncSession, phone: str):
    stmt = (
        select(SuratPermohonan, Warga)
        .join(Warga, SuratPermohonan.warga_id == Warga.id)
        .where(Warga.no_hp == phone)
        .order_by(SuratPermohonan.created_at.desc())
        .limit(5)
    )
    result = await session.execute(stmt)
    rows = result.all()

    if not rows:
        await wa_client.send_text(phone, "📋 Anda belum pernah membuat surat. Ketik *halo* untuk mulai.")
        return

    jenis_map = {"sktm": "SKTM", "domisili": "Domisili", "usaha": "Surat Usaha"}
    lines = []
    for i, (surat, warga) in enumerate(rows, 1):
        jenis = jenis_map.get(surat.jenis_surat, surat.jenis_surat)
        tanggal = surat.created_at.strftime("%d/%m/%Y %H:%M") if surat.created_at else "-"
        lines.append(f"{i}. *{jenis}* — {surat.nomor_surat}\n   Status: {surat.status} | {tanggal}")

    msg = f"📋 *Riwayat Surat Anda* (5 terakhir):\n\n" + "\n\n".join(lines) + "\n\nKetik *halo* untuk membuat surat baru."
    await wa_client.send_text(phone, msg)


async def _handle_generate_surat(session: AsyncSession, data: dict):
    phone = data["phone"]
    jenis_surat = data["jenis_surat"]

    stmt = select(Warga).where(Warga.nik == data["nik"])
    result = await session.execute(stmt)
    warga = result.scalar_one_or_none()

    if warga is None:
        warga = Warga(
            nama=data["nama"],
            nik=data["nik"],
            alamat=data["alamat"],
            pekerjaan=data["pekerjaan"],
            no_hp=phone,
        )
        session.add(warga)
        await session.flush()
    else:
        warga.nama = data["nama"]
        warga.alamat = data["alamat"]
        warga.pekerjaan = data["pekerjaan"]
        warga.no_hp = phone

    permohonan = SuratPermohonan(
        warga_id=warga.id,
        jenis_surat=jenis_surat,
        keperluan=data.get("keperluan", ""),
        nomor_surat="TEMP",
        status="proses",
    )
    session.add(permohonan)
    await session.flush()

    nomor_surat = _generate_nomor_surat(jenis_surat, permohonan.id)
    permohonan.nomor_surat = nomor_surat

    pdf_path = generate_pdf(jenis_surat, data, nomor_surat)
    permohonan.file_path = pdf_path
    permohonan.status = "selesai"

    await session.commit()

    jenis_map = {
        "sktm": "SKTM",
        "domisili": "Surat Domisili",
        "usaha": "Surat Keterangan Usaha",
    }
    surat_name = jenis_map.get(jenis_surat, jenis_surat)
    filename = f"{surat_name.replace(' ', '_')}_{data['nama'].replace(' ', '_')}.pdf"

    await asyncio.sleep(5)

    media_url = await wa_client.upload_file(pdf_path)
    if not media_url:
        logger.error(f"Upload PDF gagal untuk {phone}")
        await wa_client.send_text(phone, f"Surat *{surat_name}* Anda sudah dibuat (No: {nomor_surat}), namun gagal diunggah. Silakan hubungi petugas desa.")
        return

    caption = f"Berikut adalah *{surat_name}* Anda.\nNomor Surat: {nomor_surat}\n\nTerima kasih telah menggunakan layanan administrasi desa."

    for attempt in range(3):
        await asyncio.sleep(3)
        send_result = await wa_client.send_media(
            to=phone,
            media_url=media_url,
            filename=filename,
            caption=caption,
        )
        if "error" not in send_result:
            logger.info(f"Surat {surat_name} berhasil dikirim ke {phone}")
            return
        logger.warning(f"Retry {attempt + 1}/3 kirim dokumen ke {phone}: {send_result}")

    logger.error(f"Gagal kirim dokumen ke {phone} setelah 3 percobaan")
    await wa_client.send_text(phone, f"Surat *{surat_name}* Anda sudah dibuat (No: {nomor_surat}), namun gagal dikirim otomatis. Silakan hubungi petugas desa.")


@app.post("/payment/webhook")
@app.post("/midtrans/webhook")
async def payment_webhook(request: Request, session: AsyncSession = Depends(get_session)):
    """
    Generic payment webhook — works with Midtrans and Flip.
    Signature/token verification is delegated to the active payment gateway adapter.
    Midtrans: POST JSON with signature_key in body.
    Flip: POST JSON with X-Callback-Token in header.
    """
    from app.payment_gateway import get_gateway
    import json as json_module

    gw = get_gateway()

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    # Verify signature/token via gateway adapter
    headers_dict = dict(request.headers)
    if not gw.verify_webhook(headers_dict, body):
        logger.warning(f"Payment webhook signature/token mismatch")
        return JSONResponse(status_code=403, content={"error": "Invalid signature"})

    # Parse webhook body into standardized format
    parsed = gw.parse_webhook_status(body)
    order_id = parsed["order_id"]
    new_status = parsed["transaction_status"]

    logger.info(f"Payment webhook: order_id={order_id} status={new_status}")

    # Find payment record
    from app.models import Payment as PaymentModel, IuranTagihan as TagihanModel, WargaRegistration

    result = await session.execute(
        select(PaymentModel).where(PaymentModel.order_id == order_id)
    )
    payment = result.scalar_one_or_none()

    if not payment:
        logger.warning(f"Payment webhook: payment not found for order_id={order_id}")
        return JSONResponse(content={"status": "ok", "message": "payment not found"})

    # Update payment status
    old_status = payment.status
    payment.status = new_status
    payment.midtrans_response = json_module.dumps(body, ensure_ascii=False)
    payment.updated_at = datetime.utcnow()

    # If payment settled, update tagihan
    if payment.status == "settlement" and old_status != "settlement":
        tagihan_result = await session.execute(
            select(TagihanModel).where(TagihanModel.id == payment.tagihan_id)
        )
        tagihan = tagihan_result.scalar_one_or_none()
        if tagihan:
            tagihan.status = "paid"
            tagihan.paid_at = datetime.utcnow()

            # Get warga info for WA notification
            warga_result = await session.execute(
                select(WargaRegistration).where(WargaRegistration.id == tagihan.warga_id)
            )
            warga = warga_result.scalar_one_or_none()
            if warga and warga.no_wa:
                nominal_str = f"Rp {payment.amount:,.0f}".replace(",", ".")
                try:
                    await wa_client.send_text(
                        warga.no_wa,
                        f"✅ *Pembayaran Berhasil!*\n\n"
                        f"• Order ID: `{order_id}`\n"
                        f"• Nominal: *{nominal_str}*\n"
                        f"• Status: *Lunas*\n\n"
                        f"Terima kasih atas pembayaran Anda! 🙏"
                    )
                except Exception as e:
                    logger.error(f"Failed to send payment confirmation to {warga.no_wa}: {e}")

    await session.commit()
    logger.info(f"Payment webhook processed: {order_id} {old_status} → {payment.status}")

    return JSONResponse(content={"status": "ok"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
