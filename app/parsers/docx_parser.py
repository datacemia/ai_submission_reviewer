from docx import Document
from app.utils.text_utils import normalize_text


def extract_text_from_docx(file_path: str) -> str:
    doc = Document(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return normalize_text("\n".join(paragraphs))