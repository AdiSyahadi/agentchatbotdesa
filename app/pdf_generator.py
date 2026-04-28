import os
import logging
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from xhtml2pdf import pisa

from app.config import settings

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")

os.makedirs(OUTPUT_DIR, exist_ok=True)

jinja_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

BULAN_INDO = [
    "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]


def _tanggal_indo() -> str:
    now = datetime.now()
    return f"{now.day} {BULAN_INDO[now.month]} {now.year}"


def _generate_nomor_surat(jenis: str, surat_id: int) -> str:
    now = datetime.now()
    prefix_map = {
        "sktm": "SKTM",
        "domisili": "SKD",
        "usaha": "SKU",
    }
    prefix = prefix_map.get(jenis, "SKT")
    return f"{surat_id:04d}/{prefix}/{now.month:02d}/{now.year}"


def generate_pdf(jenis_surat: str, data: dict, nomor_surat: str) -> str:
    template_map = {
        "sktm": "sktm.html",
        "domisili": "domisili.html",
        "usaha": "surat_usaha.html",
    }

    template_file = template_map.get(jenis_surat)
    if not template_file:
        raise ValueError(f"Jenis surat tidak dikenal: {jenis_surat}")

    template = jinja_env.get_template(template_file)

    context = {
        **data,
        "nomor_surat": nomor_surat,
        "tanggal_surat": _tanggal_indo(),
        "nama_desa": settings.NAMA_DESA,
        "nama_kecamatan": settings.NAMA_KECAMATAN,
        "nama_kabupaten": settings.NAMA_KABUPATEN,
        "nama_provinsi": settings.NAMA_PROVINSI,
        "nama_kepala_desa": settings.NAMA_KEPALA_DESA,
        "nip_kepala_desa": settings.NIP_KEPALA_DESA,
    }

    html_content = template.render(context)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = data.get("nama", "unknown").replace(" ", "_").lower()
    filename = f"{jenis_surat}_{safe_name}_{timestamp}.pdf"
    output_path = os.path.join(OUTPUT_DIR, filename)

    with open(output_path, "wb") as f:
        pisa_status = pisa.CreatePDF(html_content, dest=f)
        if pisa_status.err:
            raise RuntimeError(f"PDF generation failed with {pisa_status.err} errors")
    logger.info(f"PDF generated: {output_path}")

    return output_path
