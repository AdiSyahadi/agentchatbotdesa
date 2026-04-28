import logging
import time
from typing import Optional

import google.generativeai as genai

from app.config import settings

logger = logging.getLogger(__name__)

# Quota cooldown: skip Gemini calls for this duration after all models exhausted
_QUOTA_COOLDOWN_SECONDS = 300  # 5 minutes
_quota_exhausted_at: float = 0.0

FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
]

_models: list = []
_configured = False


def _get_models() -> list:
    global _models, _configured
    if not _configured and settings.GEMINI_API_KEY:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _models = [genai.GenerativeModel(m) for m in FALLBACK_MODELS]
        _configured = True
    return _models


def _is_quota_error(e: Exception) -> bool:
    err = str(e).lower()
    return "429" in err or "quota" in err or "resourceexhausted" in err


SYSTEM_PROMPT = """Kamu adalah asisten chatbot administrasi desa. Tugasmu:

1. INTENT DETECTION: Tentukan apa yang dimaksud user dari pesannya.
   - Jika user ingin membuat surat, tentukan jenis surat: "sktm", "domisili", atau "usaha"
   - Jika user menyapa atau butuh bantuan, kembalikan intent "greeting"
   - Jika user ingin membatalkan, kembalikan intent "cancel"
   - Jika tidak jelas, kembalikan intent "unknown"

2. DATA VALIDATION: Jika diminta validasi, periksa apakah data yang diberikan user masuk akal.

PENTING: Jawab HANYA dengan format JSON, tanpa teks lain.
"""


def is_quota_cooled_down() -> bool:
    """Check if Gemini intent detection is in quota cooldown."""
    global _quota_exhausted_at
    if _quota_exhausted_at == 0.0:
        return False
    return (time.time() - _quota_exhausted_at) < _QUOTA_COOLDOWN_SECONDS


async def detect_intent(user_message: str) -> Optional[str]:
    """Detect user intent using Gemini. Returns: sktm, domisili, usaha, greeting, cancel, or None."""
    global _quota_exhausted_at

    if is_quota_cooled_down():
        logger.info(f"Gemini intent skipped: quota cooldown")
        return None

    models = _get_models()
    if not models:
        return None

    prompt = f"""{SYSTEM_PROMPT}

Pesan user: "{user_message}"

Tentukan intent user. Jawab HANYA dengan JSON:
{{"intent": "sktm" | "domisili" | "usaha" | "greeting" | "cancel" | "unknown"}}
"""
    import json
    for i, model in enumerate(models):
        try:
            response = model.generate_content(prompt)
            text = response.text.strip()
            text = text.replace("```json", "").replace("```", "").strip()

            result = json.loads(text)
            intent = result.get("intent", "unknown")
            logger.info(f"Gemini intent ({FALLBACK_MODELS[i]}): '{user_message}' -> {intent}")
            return intent
        except Exception as e:
            if _is_quota_error(e) and i < len(models) - 1:
                logger.warning(f"Gemini {FALLBACK_MODELS[i]} quota exceeded, falling back to {FALLBACK_MODELS[i+1]}")
                continue
            if _is_quota_error(e):
                logger.warning(f"Gemini intent: all models exhausted, cooldown {_QUOTA_COOLDOWN_SECONDS}s")
                _quota_exhausted_at = time.time()
            else:
                logger.warning(f"Gemini intent detection failed ({FALLBACK_MODELS[i]}): {e}")
            return None

    _quota_exhausted_at = time.time()
    return None


async def smart_validate(field_name: str, value: str, context: str = "") -> Optional[str]:
    """Use Gemini to validate input more intelligently. Returns error message or None if valid."""
    models = _get_models()
    if not models:
        return None

    prompt = f"""{SYSTEM_PROMPT}

User sedang mengisi field "{field_name}" untuk surat administrasi desa.
Nilai yang dimasukkan: "{value}"
{f'Konteks: {context}' if context else ''}

Apakah nilai ini masuk akal untuk field "{field_name}"?
Jawab HANYA dengan JSON:
{{"valid": true/false, "reason": "alasan jika tidak valid"}}
"""
    import json
    for i, model in enumerate(models):
        try:
            response = model.generate_content(prompt)
            text = response.text.strip()
            text = text.replace("```json", "").replace("```", "").strip()

            result = json.loads(text)
            if not result.get("valid", True):
                return result.get("reason", "Data tidak valid.")
            return None
        except Exception as e:
            if _is_quota_error(e) and i < len(models) - 1:
                logger.warning(f"Gemini {FALLBACK_MODELS[i]} quota exceeded, falling back to {FALLBACK_MODELS[i+1]}")
                continue
            logger.warning(f"Gemini validation failed ({FALLBACK_MODELS[i]}): {e}")
            return None
    return None


async def generate_friendly_response(context: str, user_message: str) -> Optional[str]:
    """Generate a friendly response using Gemini for better UX."""
    models = _get_models()
    if not models:
        return None

    prompt = f"""Kamu adalah chatbot administrasi desa yang ramah dan helpful.
Konteks: {context}
Pesan user: "{user_message}"

Berikan respons yang ramah, singkat (maks 2 kalimat), dan dalam bahasa Indonesia.
Gunakan format WhatsApp (*bold* untuk penekanan).
Jawab HANYA dengan teks respons, tanpa JSON.
"""
    for i, model in enumerate(models):
        try:
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            if _is_quota_error(e) and i < len(models) - 1:
                logger.warning(f"Gemini {FALLBACK_MODELS[i]} quota exceeded, falling back to {FALLBACK_MODELS[i+1]}")
                continue
            logger.warning(f"Gemini response generation failed ({FALLBACK_MODELS[i]}): {e}")
            return None
    return None
