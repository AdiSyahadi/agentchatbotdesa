import logging
import time
from typing import Optional

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferWindowMemory
from langchain.prompts import PromptTemplate

from app.config import settings
from app.rag_store import get_retriever

logger = logging.getLogger(__name__)

# Quota cooldown: skip RAG calls for this duration after all models exhausted
_QUOTA_COOLDOWN_SECONDS = 300  # 5 minutes
_quota_exhausted_at: float = 0.0

FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
]

_memories: dict[str, ConversationBufferWindowMemory] = {}

SYSTEM_TEMPLATE = """Kamu adalah asisten informasi Desa {nama_desa}, Kecamatan {nama_kecamatan}, Kabupaten {nama_kabupaten}, Provinsi {nama_provinsi}.

Kepala Desa saat ini: {nama_kepala_desa}

Tugasmu:
- Menjawab pertanyaan warga tentang program desa, transparansi dana desa, prosedur administrasi, jadwal pelayanan, dan informasi umum desa.
- Jawab berdasarkan dokumen yang diberikan (context). Jika informasi tidak ada di dokumen, katakan dengan jujur bahwa kamu belum punya informasinya dan sarankan warga menghubungi kantor desa langsung.
- Gunakan bahasa Indonesia yang ramah, sopan, dan mudah dipahami.
- Jika warga ingin membuat surat (SKTM, Domisili, Usaha), arahkan mereka untuk ketik "menu" untuk masuk ke layanan pembuatan surat.
- Jangan mengarang data atau angka yang tidak ada di dokumen.
- Jawab singkat dan jelas, maksimal 3-4 paragraf.
- PENTING: Jika pertanyaan tidak berkaitan dengan desa, administrasi, surat, atau layanan publik (misalnya obrolan santai, pertanyaan pribadi, atau topik di luar konteks desa), JANGAN dijawab. Balas dengan: "Maaf, saya hanya bisa membantu terkait informasi dan layanan Desa {nama_desa}. Ketik *menu* untuk membuat surat atau tanyakan seputar program dan layanan desa."

Context dari dokumen desa:
{context}

Riwayat percakapan:
{chat_history}

Pertanyaan warga: {question}

Jawaban:"""

QA_PROMPT = PromptTemplate(
    template=SYSTEM_TEMPLATE,
    input_variables=["context", "chat_history", "question"],
    partial_variables={
        "nama_desa": settings.NAMA_DESA,
        "nama_kecamatan": settings.NAMA_KECAMATAN,
        "nama_kabupaten": settings.NAMA_KABUPATEN,
        "nama_provinsi": settings.NAMA_PROVINSI,
        "nama_kepala_desa": settings.NAMA_KEPALA_DESA,
    },
)


def _get_memory(phone: str) -> ConversationBufferWindowMemory:
    if phone not in _memories:
        _memories[phone] = ConversationBufferWindowMemory(
            k=10,
            memory_key="chat_history",
            return_messages=True,
            output_key="answer",
        )
    return _memories[phone]


def _is_quota_error(e: Exception) -> bool:
    err = str(e).lower()
    return "429" in err or "quota" in err or "resourceexhausted" in err


def _get_chain(phone: str, model_name: str) -> Optional[ConversationalRetrievalChain]:
    if not settings.GEMINI_API_KEY:
        logger.warning("Gemini API key not configured")
        return None

    retriever = get_retriever(k=3)
    if retriever is None:
        logger.warning("No retriever available (vectorstore empty)")
        return None

    llm = ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=settings.GEMINI_API_KEY,
        temperature=0.3,
        max_output_tokens=1024,
    )

    memory = _get_memory(phone)

    chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        memory=memory,
        combine_docs_chain_kwargs={"prompt": QA_PROMPT},
        return_source_documents=False,
        verbose=False,
    )

    return chain


_QUOTA_EXHAUSTED_MSG = (
    "Maaf, layanan tanya jawab sedang sibuk saat ini.\n\n"
    "Silakan coba lagi dalam beberapa menit, atau gunakan layanan lain:\n"
    "\u2022 Ketik *menu* \u2014 menu pembuatan surat\n"
    "\u2022 Ketik *riwayat* \u2014 cek riwayat surat"
)


def is_quota_cooled_down() -> bool:
    """Check if we're still in quota cooldown period. Used by conversation.py to skip RAG."""
    global _quota_exhausted_at
    if _quota_exhausted_at == 0.0:
        return False
    return (time.time() - _quota_exhausted_at) < _QUOTA_COOLDOWN_SECONDS


async def ask_rag(phone: str, question: str) -> str:
    global _quota_exhausted_at

    # Skip if still in cooldown from previous quota exhaustion
    if is_quota_cooled_down():
        remaining = int(_QUOTA_COOLDOWN_SECONDS - (time.time() - _quota_exhausted_at))
        logger.info(f"RAG skipped for {phone}: quota cooldown ({remaining}s remaining)")
        return _QUOTA_EXHAUSTED_MSG

    for i, model_name in enumerate(FALLBACK_MODELS):
        chain = _get_chain(phone, model_name)
        if chain is None:
            return "Maaf, layanan informasi desa belum tersedia saat ini. Silakan hubungi kantor desa langsung."

        try:
            result = await chain.ainvoke({"question": question})
            answer = result.get("answer", "").strip()

            if not answer:
                return "Maaf, saya tidak menemukan informasi yang Anda cari. Silakan hubungi kantor desa langsung atau coba pertanyaan lain."

            # Success — clear any previous cooldown
            _quota_exhausted_at = 0.0
            logger.info(f"RAG answer ({model_name}) for {phone}: {answer[:100]}...")
            return answer

        except Exception as e:
            if _is_quota_error(e) and i < len(FALLBACK_MODELS) - 1:
                logger.warning(f"RAG {model_name} quota exceeded, falling back to {FALLBACK_MODELS[i+1]}")
                continue
            if _is_quota_error(e):
                logger.warning(f"RAG all models quota exhausted (last: {model_name}), cooldown {_QUOTA_COOLDOWN_SECONDS}s")
                _quota_exhausted_at = time.time()
                return _QUOTA_EXHAUSTED_MSG
            logger.error(f"RAG query error ({model_name}) for {phone}: {e}", exc_info=True)
            return "Maaf, terjadi kesalahan saat mencari informasi. Silakan coba lagi atau hubungi kantor desa."

    _quota_exhausted_at = time.time()
    return _QUOTA_EXHAUSTED_MSG


def clear_memory(phone: str):
    if phone in _memories:
        del _memories[phone]
        logger.info(f"Cleared RAG memory for {phone}")
