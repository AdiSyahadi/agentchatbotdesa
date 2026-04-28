import logging
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RT, IuranType

logger = logging.getLogger(__name__)


async def seed_data(session: AsyncSession):
    """Seed initial data for RT and IuranType if tables are empty."""

    # Seed RT data
    rt_count = await session.scalar(select(func.count(RT.id)))
    if rt_count == 0:
        rt_data = [
            RT(nomor_rt="001", nomor_rw="001", nama_ketua="Haji Udin"),
            RT(nomor_rt="002", nomor_rw="001", nama_ketua="Pak Dedi"),
            RT(nomor_rt="003", nomor_rw="001", nama_ketua="Bu Siti"),
            RT(nomor_rt="001", nomor_rw="002", nama_ketua="Pak Agus"),
            RT(nomor_rt="002", nomor_rw="002", nama_ketua="Pak Rahmat"),
            RT(nomor_rt="003", nomor_rw="002", nama_ketua="Bu Rina"),
        ]
        session.add_all(rt_data)
        logger.info(f"Seeded {len(rt_data)} RT records")

    # Seed IuranType data
    iuran_count = await session.scalar(select(func.count(IuranType.id)))
    if iuran_count == 0:
        iuran_data = [
            IuranType(
                nama="Iuran RT",
                deskripsi="Iuran wajib bulanan warga RT untuk keamanan dan kebersihan lingkungan",
                nominal=50000,
            ),
            IuranType(
                nama="Iuran Sampah",
                deskripsi="Iuran bulanan untuk pengelolaan sampah dan kebersihan",
                nominal=25000,
            ),
            IuranType(
                nama="Iuran Keamanan",
                deskripsi="Iuran bulanan untuk pos ronda dan keamanan lingkungan",
                nominal=30000,
            ),
        ]
        session.add_all(iuran_data)
        logger.info(f"Seeded {len(iuran_data)} IuranType records")

    await session.commit()
