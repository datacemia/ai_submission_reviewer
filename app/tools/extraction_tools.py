import os
from app.parsers.docx_parser import extract_text_from_docx
from app.parsers.pdf_parser import extract_text_from_pdf
from app.utils.text_utils import count_words


def extract_text_from_file(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".docx":
        return extract_text_from_docx(file_path)
    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    raise ValueError(f"Unsupported file type: {ext}")


def extract_basic_metadata(text: str) -> dict:
    return {
        "word_count": count_words(text),
        "char_count": len(text),
        "has_references": "references" in text.lower(),
    }