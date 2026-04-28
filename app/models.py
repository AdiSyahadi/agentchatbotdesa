import json
from datetime import datetime
from sqlalchemy import Integer, BigInteger, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Warga(Base):
    __tablename__ = "warga"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nama: Mapped[str] = mapped_column(String(100), nullable=False)
    nik: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    alamat: Mapped[str] = mapped_column(Text, nullable=False)
    pekerjaan: Mapped[str] = mapped_column(String(50), nullable=False)
    no_hp: Mapped[str] = mapped_column(String(15), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    permohonan: Mapped[list["SuratPermohonan"]] = relationship(back_populates="warga")


class SuratPermohonan(Base):
    __tablename__ = "surat_permohonan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    warga_id: Mapped[int] = mapped_column(Integer, ForeignKey("warga.id"), nullable=False)
    jenis_surat: Mapped[str] = mapped_column(String(50), nullable=False)
    keperluan: Mapped[str] = mapped_column(Text, nullable=True)
    nomor_surat: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="dibuat")
    file_path: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    warga: Mapped["Warga"] = relationship(back_populates="permohonan")


class WargaRegistration(Base):
    __tablename__ = "warga_registration"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nik: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    nama: Mapped[str] = mapped_column(String(100), nullable=False)
    no_wa: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, approved, rejected
    rejected_reason: Mapped[str] = mapped_column(Text, nullable=True)
    rejection_count: Mapped[int] = mapped_column(Integer, default=0)
    verified_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChatSession(Base):
    __tablename__ = "chat_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    contact_name: Mapped[str] = mapped_column(String(100), nullable=True)
    state: Mapped[str] = mapped_column(String(20), default="idle")
    jenis_surat: Mapped[str] = mapped_column(String(50), nullable=True)
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    data_json: Mapped[str] = mapped_column(Text, default="{}")
    last_activity: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def get_data(self) -> dict:
        return json.loads(self.data_json) if self.data_json else {}

    def set_data(self, data: dict):
        self.data_json = json.dumps(data, ensure_ascii=False)


class RT(Base):
    __tablename__ = "rt"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nomor_rt: Mapped[str] = mapped_column(String(5), nullable=False)
    nomor_rw: Mapped[str] = mapped_column(String(5), nullable=False)
    nama_ketua: Mapped[str] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    iuran_tagihan: Mapped[list["IuranTagihan"]] = relationship(back_populates="rt")


class IuranType(Base):
    __tablename__ = "iuran_type"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nama: Mapped[str] = mapped_column(String(100), nullable=False)
    deskripsi: Mapped[str] = mapped_column(Text, nullable=True)
    nominal: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    iuran_tagihan: Mapped[list["IuranTagihan"]] = relationship(back_populates="iuran_type")


class IuranTagihan(Base):
    __tablename__ = "iuran_tagihan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    warga_id: Mapped[int] = mapped_column(Integer, ForeignKey("warga_registration.id"), nullable=False)
    iuran_type_id: Mapped[int] = mapped_column(Integer, ForeignKey("iuran_type.id"), nullable=False)
    rt_id: Mapped[int] = mapped_column(Integer, ForeignKey("rt.id"), nullable=False)
    bulan: Mapped[str] = mapped_column(String(7), nullable=False)  # format: YYYY-MM
    nominal: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="unpaid")  # unpaid, pending, paid
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    warga: Mapped["WargaRegistration"] = relationship()
    iuran_type: Mapped["IuranType"] = relationship(back_populates="iuran_tagihan")
    rt: Mapped["RT"] = relationship(back_populates="iuran_tagihan")
    payment: Mapped["Payment"] = relationship(back_populates="tagihan", uselist=False)


class Payment(Base):
    __tablename__ = "payment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tagihan_id: Mapped[int] = mapped_column(Integer, ForeignKey("iuran_tagihan.id"), nullable=False)
    order_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payment_type: Mapped[str] = mapped_column(String(50), nullable=True)  # qris, bank_transfer, etc
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, settlement, expire, cancel
    midtrans_response: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tagihan: Mapped["IuranTagihan"] = relationship(back_populates="payment")
