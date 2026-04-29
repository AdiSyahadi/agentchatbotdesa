import logging
import random
from typing import Optional
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatSession, WargaRegistration
from app.config import settings
from app.validators import (
    validate_nama, validate_nik, validate_alamat,
    validate_pekerjaan, validate_keperluan,
    validate_nama_usaha, validate_jenis_usaha, validate_alamat_usaha,
)

logger = logging.getLogger(__name__)

SURAT_TYPES = {
    "sktm": "Surat Keterangan Tidak Mampu (SKTM)",
    "domisili": "Surat Keterangan Domisili",
    "usaha": "Surat Keterangan Usaha",
}

SKTM_STEPS = [
    {"field": "nama", "prompt": "Masukkan *nama lengkap* sesuai KTP Anda.", "example": "Contoh: _Budi Santoso_", "validator": validate_nama},
    {"field": "nik", "prompt": "Masukkan *NIK* Anda (16 digit sesuai KTP).", "example": "Contoh: _3204112233445566_", "validator": validate_nik},
    {"field": "alamat", "prompt": "Masukkan *alamat lengkap* tempat tinggal Anda.", "example": "Contoh: _Jl. Merdeka No. 15, RT 02/RW 05, Sukamaju_", "validator": validate_alamat},
    {"field": "pekerjaan", "prompt": "Apa *pekerjaan* Anda saat ini?", "example": "Contoh: _Buruh, Petani, Pedagang, Ibu Rumah Tangga_", "validator": validate_pekerjaan},
    {"field": "keperluan", "prompt": "Untuk *keperluan* apa surat ini dibutuhkan?", "example": "Contoh: _Mengajukan bantuan pendidikan anak_", "validator": validate_keperluan},
]

DOMISILI_STEPS = [
    {"field": "nama", "prompt": "Masukkan *nama lengkap* sesuai KTP Anda.", "example": "Contoh: _Budi Santoso_", "validator": validate_nama},
    {"field": "nik", "prompt": "Masukkan *NIK* Anda (16 digit sesuai KTP).", "example": "Contoh: _3204112233445566_", "validator": validate_nik},
    {"field": "alamat", "prompt": "Masukkan *alamat lengkap* domisili Anda saat ini.", "example": "Contoh: _Jl. Merdeka No. 15, RT 02/RW 05, Sukamaju_", "validator": validate_alamat},
    {"field": "pekerjaan", "prompt": "Apa *pekerjaan* Anda saat ini?", "example": "Contoh: _Karyawan Swasta, PNS, Wiraswasta_", "validator": validate_pekerjaan},
    {"field": "keperluan", "prompt": "Untuk *keperluan* apa surat domisili ini?", "example": "Contoh: _Persyaratan pembukaan rekening bank_", "validator": validate_keperluan},
]

USAHA_STEPS = [
    {"field": "nama", "prompt": "Masukkan *nama lengkap* pemilik usaha sesuai KTP.", "example": "Contoh: _Budi Santoso_", "validator": validate_nama},
    {"field": "nik", "prompt": "Masukkan *NIK* Anda (16 digit sesuai KTP).", "example": "Contoh: _3204112233445566_", "validator": validate_nik},
    {"field": "alamat", "prompt": "Masukkan *alamat lengkap* tempat tinggal Anda.", "example": "Contoh: _Jl. Merdeka No. 15, RT 02/RW 05, Sukamaju_", "validator": validate_alamat},
    {"field": "pekerjaan", "prompt": "Apa *pekerjaan* Anda?", "example": "Contoh: _Wiraswasta_", "validator": validate_pekerjaan},
    {"field": "nama_usaha", "prompt": "Masukkan *nama usaha* Anda.", "example": "Contoh: _Warung Makan Bu Sari_", "validator": validate_nama_usaha},
    {"field": "jenis_usaha", "prompt": "Apa *jenis usaha* Anda?", "example": "Contoh: _Warung Makan, Bengkel Motor, Toko Kelontong_", "validator": validate_jenis_usaha},
    {"field": "alamat_usaha", "prompt": "Masukkan *alamat lengkap usaha* Anda.", "example": "Contoh: _Jl. Pasar Baru No. 5, Sukamaju_", "validator": validate_alamat_usaha},
]

STEPS_MAP = {
    "sktm": SKTM_STEPS,
    "domisili": DOMISILI_STEPS,
    "usaha": USAHA_STEPS,
}

SESSION_TIMEOUT_MINUTES = 30

MENU_TEXT = (
    "1️⃣ *SKTM* — Surat Keterangan Tidak Mampu\n"
    "2️⃣ *Domisili* — Surat Keterangan Domisili\n"
    "3️⃣ *Usaha* — Surat Keterangan Usaha\n\n"
    "Ketik angka (1/2/3) atau nama suratnya."
)

ACK_RESPONSES = [
    "Baik, sudah dicatat ✅",
    "Oke, tercatat ✅",
    "Siap, sudah saya simpan ✅",
    "Terima kasih ✅",
]


def _get_greeting(name: str = "") -> str:
    sapaan = f" {name}" if name else ""
    hour = datetime.utcnow().hour + 7
    if 5 <= hour < 11:
        waktu = "Selamat pagi"
    elif 11 <= hour < 15:
        waktu = "Selamat siang"
    elif 15 <= hour < 18:
        waktu = "Selamat sore"
    else:
        waktu = "Selamat malam"

    return (
        f"{waktu}{sapaan}! 👋\n"
        f"Saya asisten *Layanan Administrasi Desa {settings.NAMA_DESA}* 🏘️\n\n"
        f"Ada yang bisa saya bantu?\n\n"
        f"📄 *Buat Surat:*\n{MENU_TEXT}\n\n"
        f"💬 *Tanya Info Desa:*\n"
        f"Langsung ketik pertanyaan Anda, misal:\n"
        f"_\"Apa saja program desa tahun ini?\"_\n"
        f"_\"Berapa anggaran dana desa?\"_\n"
        f"_\"Bagaimana prosedur buat SKTM?\"_"
    )


def _get_cancel_msg(name: str = "") -> str:
    sapaan = f" {name}" if name else ""
    return f"Baik{sapaan}, proses dibatalkan. Ketik *menu* kapan saja kalau butuh bantuan lagi 🙏"

HELP_KEYWORDS = {"halo", "hai", "hi", "hello", "menu", "mulai", "start", "help", "bantuan"}
CANCEL_KEYWORDS = {"batal", "cancel", "keluar", "exit", "stop"}
DAFTAR_KEYWORDS = {"daftar", "register", "registrasi", "pendaftaran"}
RIWAYAT_KEYWORDS = {"riwayat", "history", "surat saya", "daftar surat"}
TANYA_KEYWORDS = {"tanya", "info", "informasi", "info desa", "program desa", "dana desa",
                   "transparansi", "anggaran", "prosedur", "jadwal", "pelayanan",
                   "bantuan", "beasiswa", "posyandu", "umkm"}


def parse_surat_choice(text: str) -> Optional[str]:
    text_lower = text.strip().lower()

    # Exact match
    if text_lower in ("1", "sktm", "surat_sktm"):
        return "sktm"
    if text_lower in ("2", "domisili", "surat domisili", "surat_domisili"):
        return "domisili"
    if text_lower in ("3", "usaha", "surat usaha", "surat_usaha"):
        return "usaha"

    # Keyword-based detection only for short messages (≤5 words)
    # Long sentences may contain keywords in a non-request context (e.g. "info tentang usaha")
    word_count = len(text_lower.split())
    if word_count <= 5:
        sktm_keywords = {"sktm", "tidak mampu", "tidakmampu"}
        domisili_keywords = {"domisili", "domisil"}
        usaha_keywords = {"usaha", "keterangan usaha"}

        for kw in sktm_keywords:
            if kw in text_lower:
                return "sktm"
        for kw in domisili_keywords:
            if kw in text_lower:
                return "domisili"
        for kw in usaha_keywords:
            if kw in text_lower:
                return "usaha"

    return None


async def _try_gemini_intent(text: str) -> Optional[str]:
    """Try to detect intent via Gemini. Returns sktm/domisili/usaha/greeting/cancel or None."""
    if not settings.GEMINI_ENABLED or not settings.GEMINI_API_KEY:
        return None
    try:
        from app.llm_client import detect_intent
        return await detect_intent(text)
    except Exception as e:
        logger.warning(f"Gemini fallback: {e}")
        return None


async def get_or_create_session(db: AsyncSession, phone: str) -> ChatSession:
    stmt = select(ChatSession).where(ChatSession.phone == phone)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if session is None:
        session = ChatSession(phone=phone, state="idle", current_step=0, data_json="{}")
        db.add(session)
        await db.flush()

    timeout = timedelta(minutes=SESSION_TIMEOUT_MINUTES)
    if session.last_activity and (datetime.utcnow() - session.last_activity > timeout):
        session.state = "idle"
        session.jenis_surat = None
        session.current_step = 0
        session.set_data({})

    session.last_activity = datetime.utcnow()
    return session


def _reset_session(session: ChatSession):
    session.state = "idle"
    session.jenis_surat = None
    session.current_step = 0
    session.set_data({})
    session.last_activity = datetime.utcnow()


async def process_message(db: AsyncSession, phone: str, message: str, contact_name: str = "") -> dict:
    """
    Process incoming message and return response.
    Returns: {"reply": str, "action": str, "data": dict}
    - action: "reply" (just text), "generate_surat" (generate PDF + send), "none"
    """
    session = await get_or_create_session(db, phone)
    session.contact_name = contact_name

    text = message.strip()
    text_lower = text.lower()

    display_name = contact_name.split()[0] if contact_name else ""

    if text_lower in CANCEL_KEYWORDS:
        _reset_session(session)
        await db.commit()
        return {"reply": _get_cancel_msg(display_name), "action": "reply", "data": {}}

    if text_lower in RIWAYAT_KEYWORDS:
        return {"reply": "", "action": "check_riwayat", "data": {"phone": phone}}

    if text_lower in DAFTAR_KEYWORDS:
        # Check if already registered
        existing = await db.execute(
            select(WargaRegistration).where(WargaRegistration.no_wa == phone)
        )
        reg = existing.scalar_one_or_none()
        if reg:
            if reg.status == "approved":
                await db.commit()
                return {"reply": f"Anda sudah terdaftar sebagai warga Desa {settings.NAMA_DESA} ✅\nNama: *{reg.nama}*\nNIK: {reg.nik}\n\nAnda bisa langsung gunakan layanan surat. Ketik *menu* untuk mulai.", "action": "reply", "data": {}}
            elif reg.status == "pending":
                await db.commit()
                return {"reply": "Pendaftaran Anda sedang *menunggu verifikasi* dari admin desa ⏳\n\nMohon tunggu, admin akan memproses pendaftaran Anda. Terima kasih.", "action": "reply", "data": {}}
            elif reg.status == "rejected":
                reason = reg.rejected_reason or "Tidak memenuhi syarat"
                if reg.rejection_count >= 3:
                    await db.commit()
                    return {"reply": f"Maaf, pendaftaran Anda sudah *ditolak {reg.rejection_count} kali*.\n\nAnda tidak dapat mendaftar ulang melalui chatbot.\nSilakan hubungi kantor desa untuk informasi lebih lanjut.", "action": "reply", "data": {}}
                # Allow re-registration: delete old record, start fresh
                await db.delete(reg)
                await db.flush()
                session.state = "registering"
                session.current_step = 0
                session.set_data({"re_register": True, "prev_rejection_count": reg.rejection_count})
                await db.commit()
                return {
                    "reply": (
                        f"Pendaftaran sebelumnya *ditolak*.\nAlasan: _{reason}_\n\n"
                        f"Silakan daftar ulang dengan data yang benar \ud83d\udcdd\n"
                        f"Kesempatan daftar ulang: *{3 - reg.rejection_count}x* lagi\n\n"
                        f"Langkah *1* dari *2*:\n"
                        f"Masukkan *NIK* Anda (16 digit sesuai KTP).\n"
                        f"Contoh: _3204112233445566_"
                    ),
                    "action": "reply",
                    "data": {},
                }
        session.state = "registering"
        session.current_step = 0
        session.set_data({})
        await db.commit()
        return {
            "reply": (
                f"📋 *Pendaftaran Warga Desa {settings.NAMA_DESA}*\n\n"
                f"Untuk menggunakan layanan pembuatan surat, Anda perlu mendaftar terlebih dahulu.\n\n"
                f"Langkah *1* dari *2*:\n"
                f"Masukkan *NIK* Anda (16 digit sesuai KTP).\n"
                f"Contoh: _3204112233445566_"
            ),
            "action": "reply",
            "data": {},
        }

    if session.state == "registering":
        return await _handle_registering(db, session, phone, text, display_name)

    if session.state == "idle":
        if text_lower in HELP_KEYWORDS:
            session.state = "choosing"
            session.last_activity = datetime.utcnow()
            await db.commit()
            return {"reply": _get_greeting(display_name), "action": "send_list_menu", "data": {"phone": phone, "display_name": display_name}}

        choice = parse_surat_choice(text)
        if choice is None:
            gemini_choice = await _try_gemini_intent(text)
            if gemini_choice in ("sktm", "domisili", "usaha"):
                choice = gemini_choice

        if choice:
            return await _start_filling_verified(db, session, phone, choice, contact_name, display_name)

        # Check if RAG quota is exhausted — skip API call, reply locally
        from app.langchain_agent import is_quota_cooled_down
        if is_quota_cooled_down():
            await db.commit()
            return {
                "reply": (
                    "Maaf, layanan tanya jawab sedang sibuk saat ini.\n\n"
                    "Silakan gunakan layanan lain:\n"
                    "• Ketik *menu* — menu pembuatan surat\n"
                    "• Ketik *riwayat* — cek riwayat surat\n\n"
                    "Atau coba tanya lagi dalam beberapa menit."
                ),
                "action": "reply",
                "data": {},
            }

        await db.commit()
        return {"reply": "", "action": "ask_rag", "data": {"phone": phone, "question": text}}

    if session.state == "choosing":
        if text_lower in HELP_KEYWORDS:
            await db.commit()
            return {"reply": _get_greeting(display_name), "action": "send_list_menu", "data": {"phone": phone, "display_name": display_name}}

        choice = parse_surat_choice(text)

        if choice is None:
            gemini_choice = await _try_gemini_intent(text)
            if gemini_choice in ("sktm", "domisili", "usaha"):
                choice = gemini_choice
            elif gemini_choice == "cancel":
                _reset_session(session)
                await db.commit()
                return {"reply": _get_cancel_msg(display_name), "action": "reply", "data": {}}

        if choice is None:
            await db.commit()
            return {
                "reply": (
                    f"Hmm, saya belum mengerti pilihan Anda{' ' + display_name if display_name else ''} 🤔\n\n"
                    f"Silakan pilih jenis surat:\n{MENU_TEXT}\n\n"
                    f"Atau ketik pertanyaan tentang desa, misal:\n"
                    f"_\"Apa program desa tahun ini?\"_"
                ),
                "action": "reply",
                "data": {},
            }

        return await _start_filling_verified(db, session, phone, choice, contact_name, display_name, show_step_count=True)

    if session.state == "filling":
        steps = STEPS_MAP[session.jenis_surat]
        current = steps[session.current_step]

        if text_lower in ("ulang", "kembali", "back") and session.current_step > 0:
            session.current_step -= 1
            prev_step = steps[session.current_step]
            total = len(steps)
            step_num = session.current_step + 1
            await db.commit()
            return {
                "reply": (
                    f"↩️ Oke, kembali ke pertanyaan sebelumnya.\n\n"
                    f"Pertanyaan *{step_num}* dari *{total}*:\n"
                    f"{prev_step['prompt']}\n{prev_step['example']}"
                ),
                "action": "reply",
                "data": {},
            }

        valid, error_msg = current["validator"](text)
        if not valid:
            await db.commit()
            return {"reply": f"⚠️ {error_msg}", "action": "reply", "data": {}}

        data = session.get_data()
        data[current["field"]] = text.strip()
        session.set_data(data)
        session.current_step += 1

        if session.current_step < len(steps):
            next_step = steps[session.current_step]
            total = len(steps)
            step_num = session.current_step + 1
            ack = random.choice(ACK_RESPONSES)
            await db.commit()
            return {
                "reply": (
                    f"{ack}\n\n"
                    f"Pertanyaan *{step_num}* dari *{total}*:\n"
                    f"{next_step['prompt']}\n{next_step['example']}"
                ),
                "action": "reply",
                "data": {},
            }

        # All steps complete — move to confirming state
        surat_name = SURAT_TYPES[session.jenis_surat]
        data_summary = "\n".join(
            f"• *{step['field'].replace('_', ' ').title()}*: {data[step['field']]}"
            for step in steps
        )
        confirm_msg = (
            f"📋 *Ringkasan Data*\n"
            f"Jenis: *{surat_name}*\n\n"
            f"{data_summary}\n\n"
            f"Sudah benar{' ' + display_name if display_name else ''}? 👆\n\n"
            f"1️⃣ *YA* — Buat surat sekarang\n"
            f"2️⃣ *TIDAK* — Isi ulang dari awal\n"
            f"3️⃣ *ULANG* — Perbaiki data terakhir\n\n"
            f"Balas dengan angka atau ketik pilihannya."
        )

        session.state = "confirming"
        await db.commit()
        return {"reply": confirm_msg, "action": "send_confirm_buttons", "data": {"phone": phone, "display_name": display_name}}

    if session.state == "confirming":
        if text_lower in ("1", "ya", "y", "yes", "benar", "betul", "ok", "oke", "confirm_yes"):
            steps = STEPS_MAP[session.jenis_surat]
            data = session.get_data()
            surat_name = SURAT_TYPES[session.jenis_surat]

            result_data = {
                "jenis_surat": session.jenis_surat,
                "phone": phone,
                **data,
            }

            _reset_session(session)
            await db.commit()

            return {
                "reply": f"✅ Siap{' ' + display_name if display_name else ''}! Surat sedang diproses... ⏳\n\nSurat *{surat_name}* Anda akan segera dikirim sebagai dokumen PDF.",
                "action": "generate_surat",
                "data": result_data,
            }

        if text_lower in ("2", "tidak", "no", "salah", "ulangi", "reset", "confirm_no"):
            jenis = session.jenis_surat
            session.state = "filling"
            session.current_step = 0
            session.set_data({"contact_name": contact_name})
            surat_name = SURAT_TYPES[jenis]
            step = STEPS_MAP[jenis][0]
            total = len(STEPS_MAP[jenis])
            await db.commit()
            return {
                "reply": (
                    f"Baik, kita mulai ulang dari awal ya 🔄\n\n"
                    f"Pertanyaan *1* dari *{total}*:\n"
                    f"{step['prompt']}\n{step['example']}"
                ),
                "action": "reply",
                "data": {},
            }

        if text_lower in ("3", "ulang", "kembali", "back", "confirm_back"):
            steps = STEPS_MAP[session.jenis_surat]
            last_step_idx = len(steps) - 1
            last_step = steps[last_step_idx]
            total = len(steps)
            session.state = "filling"
            session.current_step = last_step_idx
            await db.commit()
            return {
                "reply": (
                    f"↩️ Oke, kita perbaiki data terakhir.\n\n"
                    f"Pertanyaan *{total}* dari *{total}*:\n"
                    f"{last_step['prompt']}\n{last_step['example']}"
                ),
                "action": "reply",
                "data": {},
            }

        await db.commit()
        return {
            "reply": (
                f"Hmm, saya butuh jawaban Anda{' ' + display_name if display_name else ''} 😊\n\n"
                f"1️⃣ *YA* — Buat surat\n"
                f"2️⃣ *TIDAK* — Isi ulang dari awal\n"
                f"3️⃣ *ULANG* — Perbaiki data terakhir\n\n"
                f"Balas dengan angka atau ketik pilihannya."
            ),
            "action": "reply",
            "data": {},
        }

    _reset_session(session)
    await db.commit()
    return {"reply": _get_greeting(display_name), "action": "reply", "data": {}}


async def _start_filling_verified(db: AsyncSession, session: ChatSession, phone: str, choice: str, contact_name: str, display_name: str, show_step_count: bool = False) -> dict:
    """Verify warga registration before starting surat filling. Auto-fills nama+nik if approved."""
    # Check registration status
    existing = await db.execute(
        select(WargaRegistration).where(WargaRegistration.no_wa == phone)
    )
    reg = existing.scalar_one_or_none()

    if reg is None:
        await db.commit()
        return {
            "reply": (
                f"Maaf, Anda belum terdaftar sebagai warga Desa {settings.NAMA_DESA} 🚫\n\n"
                f"Untuk menggunakan layanan pembuatan surat, silakan *daftar* terlebih dahulu.\n"
                f"Ketik *daftar* untuk memulai pendaftaran."
            ),
            "action": "reply",
            "data": {},
        }

    if reg.status == "pending":
        await db.commit()
        return {
            "reply": "Pendaftaran Anda sedang *menunggu verifikasi* dari admin desa ⏳\n\nMohon tunggu, admin akan memproses pendaftaran Anda. Setelah disetujui, Anda bisa membuat surat.",
            "action": "reply",
            "data": {},
        }

    if reg.status == "rejected":
        reason = reg.rejected_reason or "Tidak memenuhi syarat"
        await db.commit()
        return {
            "reply": f"Maaf, pendaftaran Anda *ditolak*.\nAlasan: _{reason}_\n\nSilakan hubungi kantor desa untuk informasi lebih lanjut.",
            "action": "reply",
            "data": {},
        }

    # status == approved — auto-fill nama + nik, skip to step 2 (alamat)
    surat_name = SURAT_TYPES[choice]
    steps = STEPS_MAP[choice]

    session.jenis_surat = choice
    session.state = "filling"
    session.current_step = 2  # Skip nama (0) and nik (1)
    session.set_data({"contact_name": contact_name, "nama": reg.nama, "nik": reg.nik})

    next_step = steps[2]
    total = len(steps)

    header = f"Baik{' ' + display_name if display_name else ''}, saya bantu buatkan *{surat_name}* ya 📝\n\n"
    autofill_info = f"✅ Data terverifikasi:\n• *Nama*: {reg.nama}\n• *NIK*: {reg.nik}\n\n"
    if show_step_count:
        header += f"Saya butuh {total - 2} data lagi dari Anda. Bisa ketik *ulang* kapan saja untuk kembali ke pertanyaan sebelumnya.\n\n"

    await db.commit()
    return {
        "reply": (
            f"{header}"
            f"{autofill_info}"
            f"Pertanyaan *3* dari *{total}*:\n"
            f"{next_step['prompt']}\n{next_step['example']}"
        ),
        "action": "reply",
        "data": {},
    }


async def _handle_registering(db: AsyncSession, session: ChatSession, phone: str, text: str, display_name: str) -> dict:
    """Handle warga registration flow: step 0 = NIK, step 1 = nama."""
    data = session.get_data()

    if session.current_step == 0:
        # Expecting NIK
        valid, error_msg = validate_nik(text)
        if not valid:
            await db.commit()
            return {"reply": f"⚠️ {error_msg}", "action": "reply", "data": {}}

        nik = text.strip()
        # Check if NIK already registered
        existing = await db.execute(
            select(WargaRegistration).where(WargaRegistration.nik == nik)
        )
        if existing.scalar_one_or_none():
            _reset_session(session)
            await db.commit()
            return {"reply": "NIK ini sudah terdaftar di sistem kami.\n\nJika Anda merasa ini salah, silakan hubungi kantor desa.", "action": "reply", "data": {}}

        data["nik"] = nik
        session.set_data(data)
        session.current_step = 1
        await db.commit()
        return {
            "reply": (
                "Baik, NIK tercatat ✅\n\n"
                "Langkah *2* dari *2*:\n"
                "Masukkan *nama lengkap* sesuai KTP Anda.\n"
                "Contoh: _Budi Santoso_"
            ),
            "action": "reply",
            "data": {},
        }

    if session.current_step == 1:
        # Expecting nama
        valid, error_msg = validate_nama(text)
        if not valid:
            await db.commit()
            return {"reply": f"⚠️ {error_msg}", "action": "reply", "data": {}}

        nama = text.strip()

        # Save registration
        prev_count = data.get("prev_rejection_count", 0)
        reg = WargaRegistration(
            nik=data["nik"],
            nama=nama,
            no_wa=phone,
            status="pending",
            rejection_count=prev_count,
        )
        db.add(reg)
        _reset_session(session)
        await db.commit()

        return {
            "reply": (
                f"✅ *Pendaftaran Berhasil!*\n\n"
                f"Nama: *{nama}*\n"
                f"NIK: {data['nik']}\n"
                f"No WA: {phone}\n\n"
                f"Status: *Menunggu Verifikasi Admin* ⏳\n\n"
                f"Admin desa akan memverifikasi data Anda. "
                f"Setelah disetujui, Anda bisa langsung menggunakan layanan pembuatan surat.\n\n"
                f"Terima kasih telah mendaftar! 🙏"
            ),
            "action": "reply",
            "data": {},
        }

    # Fallback — should not happen
    _reset_session(session)
    await db.commit()
    return {"reply": "Terjadi kesalahan pada proses pendaftaran. Silakan ketik *daftar* untuk mengulang.", "action": "reply", "data": {}}


