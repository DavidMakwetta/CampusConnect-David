
from functools import lru_cache

from app.rag.vectorstore import get_or_create_vectorstore


@lru_cache(maxsize=1)
def get_vectorstore():
    """Load the saved index once and reuse it."""
    return get_or_create_vectorstore()


def retrieve_documents(question, k=4):
    """Retrieve relevant document chunks for a question."""
    vectorstore = get_vectorstore()

    return vectorstore.similarity_search_with_score(
        question,
        k=k,
    )
