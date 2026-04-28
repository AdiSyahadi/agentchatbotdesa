import re


def validate_nik(nik: str) -> tuple[bool, str]:
    nik = nik.strip()
    if not nik.isdigit():
        return False, "NIK harus berupa angka. Mohon masukkan NIK yang benar."
    if len(nik) != 16:
        return False, f"NIK harus 16 digit, Anda memasukkan {len(nik)} digit. Mohon masukkan NIK yang benar."
    return True, ""


def validate_nama(nama: str) -> tuple[bool, str]:
    nama = nama.strip()
    if len(nama) < 3:
        return False, "Nama terlalu pendek. Mohon masukkan nama lengkap Anda."
    if not re.match(r"^[a-zA-Z\s'.]+$", nama):
        return False, "Nama hanya boleh berisi huruf, spasi, titik, dan apostrof."
    return True, ""


def validate_alamat(alamat: str) -> tuple[bool, str]:
    alamat = alamat.strip()
    if len(alamat) < 10:
        return False, "Alamat terlalu pendek. Mohon masukkan alamat lengkap Anda."
    if alamat.isdigit():
        return False, "Alamat tidak boleh hanya berisi angka. Mohon masukkan alamat lengkap (contoh: Jl. Merdeka No. 15, RT 02/RW 05, Sukamaju)."
    if not re.search(r'[a-zA-Z]', alamat):
        return False, "Alamat harus mengandung huruf. Mohon masukkan alamat lengkap Anda."
    return True, ""


def validate_pekerjaan(pekerjaan: str) -> tuple[bool, str]:
    pekerjaan = pekerjaan.strip()
    if len(pekerjaan) < 2:
        return False, "Mohon masukkan pekerjaan Anda dengan benar."
    return True, ""


def validate_keperluan(keperluan: str) -> tuple[bool, str]:
    keperluan = keperluan.strip()
    if len(keperluan) < 5:
        return False, "Mohon jelaskan keperluan surat Anda dengan lebih detail."
    return True, ""


def validate_nama_usaha(nama_usaha: str) -> tuple[bool, str]:
    nama_usaha = nama_usaha.strip()
    if len(nama_usaha) < 3:
        return False, "Nama usaha terlalu pendek. Mohon masukkan nama usaha yang benar."
    return True, ""


def validate_jenis_usaha(jenis_usaha: str) -> tuple[bool, str]:
    jenis_usaha = jenis_usaha.strip()
    if len(jenis_usaha) < 3:
        return False, "Jenis usaha terlalu pendek. Mohon masukkan jenis usaha yang benar."
    return True, ""


def validate_alamat_usaha(alamat_usaha: str) -> tuple[bool, str]:
    alamat_usaha = alamat_usaha.strip()
    if len(alamat_usaha) < 10:
        return False, "Alamat usaha terlalu pendek. Mohon masukkan alamat usaha yang lengkap."
    if alamat_usaha.isdigit():
        return False, "Alamat usaha tidak boleh hanya berisi angka. Mohon masukkan alamat usaha yang lengkap."
    if not re.search(r'[a-zA-Z]', alamat_usaha):
        return False, "Alamat usaha harus mengandung huruf. Mohon masukkan alamat usaha yang lengkap."
    return True, ""
