
from pathlib import Path

from langchain_community.vectorstores import FAISS

from app.rag.embeddings import get_embeddings
from app.rag.loader import load_documents
from app.rag.chunker import split_documents


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INDEX_DIR = PROJECT_ROOT / "knowledge" / "faiss_index"


def build_vectorstore():
    """Build the FAISS index from the corpus."""
    documents = load_documents()
    chunks = split_documents(documents)
    embeddings = get_embeddings()

    return FAISS.from_documents(chunks, embeddings)


def get_or_create_vectorstore():
    """Load a saved index or create it if it does not exist."""
    embeddings = get_embeddings()

    if (INDEX_DIR / "index.faiss").exists():
        return FAISS.load_local(
            str(INDEX_DIR),
            embeddings,
            allow_dangerous_deserialization=True,
        )

    vectorstore = build_vectorstore()
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(str(INDEX_DIR))

    return vectorstore
