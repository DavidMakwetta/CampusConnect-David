
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader


# Project root: CampusConnect
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Folder containing the CoCIS PDF documents
CORPUS_DIR = PROJECT_ROOT / "knowledge" / "Corpus"


def load_documents():
    """Load PDF documents and preserve their source filenames."""
    documents = []

    pdf_files = sorted(CORPUS_DIR.glob("*.pdf"))

    for pdf_file in pdf_files:
        loader = PyPDFLoader(str(pdf_file))
        documents.extend(
    doc for doc in loader.load()
    if doc.page_content.strip()
)

    return documents
