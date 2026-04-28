import os
import logging
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)

os.makedirs("data", exist_ok=True)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=3600,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Initialize database with retry for MySQL startup delay."""
    from app.seeder import seed_data

    max_retries = 5
    for attempt in range(max_retries):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database initialized successfully")
            # Seed initial data
            async with async_session() as session:
                await seed_data(session)
            return
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"DB init attempt {attempt + 1}/{max_retries} failed: {e}. Retrying in 3s...")
                await asyncio.sleep(3)
            else:
                logger.error(f"DB init failed after {max_retries} attempts: {e}")
                raise


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
