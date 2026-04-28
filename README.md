# Chatbot Administrasi Desa

Chatbot WhatsApp untuk pelayanan administrasi desa. Warga dapat membuat surat administrasi (SKTM, Surat Domisili, Surat Usaha) melalui WhatsApp.

## Tech Stack

- **Python 3.10+** + **FastAPI** — webhook server
- **SQLite** (async via aiosqlite) — database
- **WeasyPrint** — HTML → PDF generation
- **Jinja2** — HTML template engine
- **httpx** — async HTTP client untuk WA API

## Arsitektur

```
WA Unofficial API (Baileys-based, existing)
  ↓ webhook POST /webhook
FastAPI Server (ini)
  ├── Conversation State Machine (in-memory per user)
  ├── Input Validation
  ├── Database (SQLite) — simpan data warga & permohonan
  ├── PDF Generator (HTML template → PDF via WeasyPrint)
  └── WA API Client — kirim teks & dokumen balik
  ↓ POST /api/v1/messages/send-text & send-media
WA Unofficial API (kirim ke user)
```

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

> **Catatan**: WeasyPrint membutuhkan system dependencies (GTK, Pango, dll).
> - **Windows**: Download [GTK3 Runtime](https://github.com/nickvdp/gtk3-windows)
> - **Ubuntu/Debian**: `sudo apt install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info`
> - **macOS**: `brew install pango`

### 2. Konfigurasi Environment

```bash
cp .env.example .env
```

Edit `.env` dan isi:
- `WA_API_BASE_URL` — Base URL WA API kamu
- `WA_API_KEY` — API key WA API
- `WA_INSTANCE_ID` — Instance ID WA yang sudah login
- Data desa (nama desa, kepala desa, dll)

### 3. Jalankan Server

```bash
python -m app.main
```

Server berjalan di `http://0.0.0.0:8000`.

### 4. Set Webhook di WA API

Arahkan webhook WA API ke:

```
http://<server-kamu>:8000/webhook
```

## Endpoint

| Method | Path | Keterangan |
|--------|------|------------|
| GET | `/health` | Health check |
| POST | `/webhook` | Menerima webhook dari WA API |

## Alur Chatbot

1. Warga kirim pesan apa saja → Bot tampilkan menu pilihan surat
2. Warga pilih jenis surat (1/2/3 atau ketik nama)
3. Bot minta data satu per satu (nama, NIK, alamat, dll)
4. Setelah lengkap, bot generate PDF surat
5. Bot kirim file PDF ke WhatsApp warga

## Jenis Surat

| Surat | Data yang Diminta |
|-------|-------------------|
| **SKTM** | Nama, NIK, Alamat, Pekerjaan, Keperluan |
| **Domisili** | Nama, NIK, Alamat, Pekerjaan, Keperluan |
| **Surat Usaha** | Nama, NIK, Alamat, Pekerjaan, Nama Usaha, Jenis Usaha, Alamat Usaha |

## Struktur Project

```
AgenticAI2026/
├── app/
│   ├── main.py           # FastAPI app + webhook
│   ├── config.py          # Environment config
│   ├── database.py        # SQLAlchemy async setup
│   ├── models.py          # DB models
│   ├── conversation.py    # State machine per user
│   ├── wa_client.py       # WA API client
│   ├── pdf_generator.py   # HTML → PDF
│   └── validators.py      # Input validation
├── templates/             # HTML template surat
├── output/                # Generated PDFs
├── .env.example
├── requirements.txt
└── README.md
```
