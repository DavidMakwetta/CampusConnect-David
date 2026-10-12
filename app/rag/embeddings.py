
from langchain_huggingface import HuggingFaceEmbeddings


def get_embeddings():
    """Create a local embedding model for CampusConnect."""
    return HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )
