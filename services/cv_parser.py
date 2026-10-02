"""Reads text from CV files using LangChain document loaders."""
from pathlib import Path

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader


def read_cv(file_path):
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        loader = PyPDFLoader(file_path)
    elif ext == ".docx":
        loader = Docx2txtLoader(file_path)
    elif ext == ".txt":
        loader = TextLoader(file_path, encoding="utf-8")
    else:
        raise ValueError(f"Unsupported CV file type: {ext}")
    return "\n".join(doc.page_content for doc in loader.load()).strip()
