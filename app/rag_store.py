import os
import logging
from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import DirectoryLoader, TextLoader

from app.config import settings

logger = logging.getLogger(__name__)

DOCS_DIR = os.getenv("DOCS_DIR", "docs")
VECTORSTORE_DIR = os.getenv("VECTORSTORE_DIR", "data/vectorstore")

_vectorstore = None


def _load_documents():
    docs_path = Path(DOCS_DIR)
    if not docs_path.exists():
        logger.warning(f"Docs directory not found: {docs_path}")
        return []

    loader = DirectoryLoader(
        str(docs_path),
        glob="**/*.md",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
    )
    documents = loader.load()
    logger.info(f"Loaded {len(documents)} documents from {docs_path}")
    return documents


def _split_documents(documents):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150,
        separators=["\n## ", "\n### ", "\n\n", "\n", " "],
    )
    chunks = splitter.split_documents(documents)
    logger.info(f"Split into {len(chunks)} chunks")
    return chunks


def build_vectorstore(force_rebuild: bool = False):
    global _vectorstore

    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=settings.GEMINI_API_KEY,
    )

    vs_path = Path(VECTORSTORE_DIR)
    if vs_path.exists() and not force_rebuild:
        try:
            _vectorstore = FAISS.load_local(
                str(vs_path), embeddings, allow_dangerous_deserialization=True
            )
            logger.info(f"Loaded existing vectorstore from {vs_path}")
            return _vectorstore
        except Exception as e:
            logger.warning(f"Failed to load vectorstore, rebuilding: {e}")

    documents = _load_documents()
    if not documents:
        logger.warning("No documents to index")
        return None

    chunks = _split_documents(documents)

    _vectorstore = FAISS.from_documents(chunks, embeddings)

    vs_path.mkdir(parents=True, exist_ok=True)
    _vectorstore.save_local(str(vs_path))
    logger.info(f"Vectorstore built and saved to {vs_path}")

    return _vectorstore


def get_vectorstore():
    global _vectorstore
    if _vectorstore is None:
        build_vectorstore()
    return _vectorstore


def get_retriever(k: int = 3):
    vs = get_vectorstore()
    if vs is None:
        return None
    return vs.as_retriever(search_kwargs={"k": k})
