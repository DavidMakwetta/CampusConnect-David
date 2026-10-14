
import os

from app.rag.retriever import retrieve_documents


def search_cocis_information(query: str) -> dict:
    """Search the CoCIS document collection and return relevant evidence."""

    if not isinstance(query, str) or not query.strip():
        return {
            "success": False,
            "error": "A non-empty search query is required.",
        }

    try:
        results = retrieve_documents(query.strip(), k=4)

        documents = []

        for document, score in results:
            documents.append({
                "source": os.path.basename(
                    document.metadata.get("source", "Unknown source")
                ),
                "page": document.metadata.get("page", "Unknown"),
                "content": document.page_content,
            })

        return {
            "success": True,
            "results": documents,
        }

    except Exception:
        return {
            "success": False,
            "error": "The CoCIS information search is temporarily unavailable.",
        }
