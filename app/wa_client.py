import asyncio
import httpx
import os
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class WAClient:
    def __init__(self):
        self.base_url = settings.WA_API_BASE_URL
        self.api_key = settings.WA_API_KEY
        self.instance_id = settings.WA_INSTANCE_ID
        self.headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

    async def resolve_lid_phone(self, lid_jid: str) -> str:
        """Resolve LID JID to real phone number via waapi. Returns phone or empty string."""
        url = f"{self.base_url}/contacts/resolve-lid"
        params = {"jid": lid_jid, "instance_id": self.instance_id}
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, params=params, headers=self.headers, timeout=10)
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    phone = data.get("phone_number", "")
                    if phone:
                        logger.info(f"LID resolved: {lid_jid} -> {phone}")
                        return phone
                logger.warning(f"LID not resolved: {lid_jid} (status {resp.status_code})")
            except Exception as e:
                logger.warning(f"resolve_lid_phone error: {e}")
        return ""

    async def send_text(self, to: str, message: str) -> dict:
        url = f"{self.base_url}/messages/send-text"
        payload = {
            "instance_id": self.instance_id,
            "to": to,
            "message": message,
        }
        logger.info(f"Sending text to {to}: {payload}")
        max_retries = 2
        for attempt in range(max_retries + 1):
            async with httpx.AsyncClient() as client:
                try:
                    resp = await client.post(url, json=payload, headers=self.headers, timeout=30)
                    if resp.status_code != 200:
                        resp_text = resp.text
                        if "Please wait" in resp_text and attempt < max_retries:
                            logger.warning(f"WA rate limit (attempt {attempt+1}), retrying in 2s...")
                            await asyncio.sleep(2)
                            continue
                        logger.error(f"WA API error {resp.status_code}: {resp_text}")
                        return {"error": resp_text}
                    logger.info(f"Pesan terkirim ke {to}")
                    return resp.json()
                except Exception as e:
                    logger.error(f"Gagal kirim pesan ke {to}: {e}")
                    return {"error": str(e)}
        return {"error": "Max retries exceeded"}

    async def upload_file(self, file_path: str) -> str:
        url = f"{self.base_url}/media/upload"
        headers = {"X-API-Key": self.api_key}
        async with httpx.AsyncClient() as client:
            try:
                with open(file_path, "rb") as f:
                    files = {"file": (os.path.basename(file_path), f, "application/pdf")}
                    resp = await client.post(url, files=files, headers=headers, timeout=60)
                    if resp.status_code != 200:
                        logger.error(f"Upload error {resp.status_code}: {resp.text}")
                        return ""
                    data = resp.json()
                    media_url = data.get("media_url") or data.get("url") or data.get("data", {}).get("url", "")
                    logger.info(f"File uploaded: {media_url}")
                    return media_url
            except Exception as e:
                logger.error(f"Gagal upload file: {e}")
                return ""

    async def send_media(self, to: str, media_url: str, filename: str, caption: str = "") -> dict:
        url = f"{self.base_url}/messages/send-media"
        payload = {
            "instance_id": self.instance_id,
            "to": to,
            "media_url": media_url,
            "media_type": "document",
            "filename": filename,
            "caption": caption,
        }
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(url, json=payload, headers=self.headers, timeout=30)
                if resp.status_code != 200:
                    logger.error(f"Send media error {resp.status_code}: {resp.text}")
                    return {"error": resp.text}
                logger.info(f"Dokumen terkirim ke {to}: {filename}")
                return resp.json()
            except Exception as e:
                logger.error(f"Gagal kirim dokumen ke {to}: {e}")
                return {"error": str(e)}


    async def send_image(self, to: str, image_url: str, caption: str = "") -> dict:
        """Send an image via URL with optional caption. Includes retry for rate limit."""
        url = f"{self.base_url}/messages/send-media"
        payload = {
            "instance_id": self.instance_id,
            "to": to,
            "media_url": image_url,
            "media_type": "image",
            "caption": caption,
        }
        max_retries = 3
        for attempt in range(max_retries + 1):
            async with httpx.AsyncClient() as client:
                try:
                    resp = await client.post(url, json=payload, headers=self.headers, timeout=30)
                    if resp.status_code != 200:
                        resp_text = resp.text
                        if "Please wait" in resp_text and attempt < max_retries:
                            delay = 3 + attempt * 2  # 3s, 5s, 7s
                            logger.warning(f"WA image rate limit (attempt {attempt+1}), retrying in {delay}s...")
                            await asyncio.sleep(delay)
                            continue
                        logger.error(f"Send image error {resp.status_code}: {resp_text}")
                        return {"error": resp_text}
                    logger.info(f"Gambar terkirim ke {to}")
                    return resp.json()
                except Exception as e:
                    logger.error(f"Gagal kirim gambar ke {to}: {e}")
                    return {"error": str(e)}
        return {"error": "Max retries exceeded"}

    async def send_buttons(self, to: str, text: str, buttons: list[dict],
                           footer: str = "", fallback_text: str = "") -> dict:
        url = f"{self.base_url}/messages/send-buttons"
        payload = {
            "instance_id": self.instance_id,
            "to": to,
            "text": text,
            "buttons": buttons,
        }
        if footer:
            payload["footer"] = footer
        if fallback_text:
            payload["fallback_text"] = fallback_text

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(url, json=payload, headers=self.headers, timeout=30)
                if resp.status_code != 200:
                    logger.warning(f"send_buttons failed {resp.status_code}: {resp.text}, using fallback text")
                    if fallback_text:
                        return await self.send_text(to, fallback_text)
                    return {"error": resp.text}
                resp_data = resp.json()
                logger.info(f"Buttons terkirim ke {to}: {resp_data}")
                return resp_data
            except Exception as e:
                logger.error(f"Gagal kirim buttons ke {to}: {e}")
                if fallback_text:
                    return await self.send_text(to, fallback_text)
                return {"error": str(e)}

    async def send_list(self, to: str, text: str, button_text: str,
                        sections: list[dict], footer: str = "", fallback_text: str = "") -> dict:
        url = f"{self.base_url}/messages/send-list"
        payload = {
            "instance_id": self.instance_id,
            "to": to,
            "text": text,
            "button_text": button_text,
            "sections": sections,
        }
        if footer:
            payload["footer"] = footer
        if fallback_text:
            payload["fallback_text"] = fallback_text

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(url, json=payload, headers=self.headers, timeout=30)
                if resp.status_code != 200:
                    logger.warning(f"send_list failed {resp.status_code}: {resp.text}, using fallback text")
                    if fallback_text:
                        return await self.send_text(to, fallback_text)
                    return {"error": resp.text}
                resp_data = resp.json()
                logger.info(f"List terkirim ke {to}: {resp_data}")
                return resp_data
            except Exception as e:
                logger.error(f"Gagal kirim list ke {to}: {e}")
                if fallback_text:
                    return await self.send_text(to, fallback_text)
                return {"error": str(e)}


wa_client = WAClient()
