import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    WA_API_BASE_URL: str = os.getenv("WA_API_BASE_URL", "http://localhost:3001/api/v1")
    WA_API_KEY: str = os.getenv("WA_API_KEY", "")
    WA_INSTANCE_ID: str = os.getenv("WA_INSTANCE_ID", "")

    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/chatbot.db")

    NAMA_DESA: str = os.getenv("NAMA_DESA", "Sukamaju")
    NAMA_KECAMATAN: str = os.getenv("NAMA_KECAMATAN", "Kecamatan Sukamaju")
    NAMA_KABUPATEN: str = os.getenv("NAMA_KABUPATEN", "Kabupaten Bandung")
    NAMA_PROVINSI: str = os.getenv("NAMA_PROVINSI", "Jawa Barat")
    NAMA_KEPALA_DESA: str = os.getenv("NAMA_KEPALA_DESA", "Asep Santoso")
    NIP_KEPALA_DESA: str = os.getenv("NIP_KEPALA_DESA", "196501011990011001")

    # Payment Gateway Switch: "midtrans" or "flip"
    PAYMENT_GATEWAY: str = os.getenv("PAYMENT_GATEWAY", "midtrans")

    # Midtrans
    MIDTRANS_SERVER_KEY: str = os.getenv("MIDTRANS_SERVER_KEY", "")
    MIDTRANS_CLIENT_KEY: str = os.getenv("MIDTRANS_CLIENT_KEY", "")
    MIDTRANS_IS_PRODUCTION: bool = os.getenv("MIDTRANS_IS_PRODUCTION", "false").lower() == "true"

    # Flip
    FLIP_SECRET_KEY: str = os.getenv("FLIP_SECRET_KEY", "")
    FLIP_VALIDATION_TOKEN: str = os.getenv("FLIP_VALIDATION_TOKEN", "")
    FLIP_IS_PRODUCTION: bool = os.getenv("FLIP_IS_PRODUCTION", "false").lower() == "true"

    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_ENABLED: bool = os.getenv("GEMINI_ENABLED", "true").lower() == "true"


settings = Settings()
