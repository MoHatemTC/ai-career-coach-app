import pdfplumber
from docx import Document


def extract_text(file_path: str) -> str:
    """
    Extract text from PDF or DOCX files.
    """

    if file_path.lower().endswith(".pdf"):
        return extract_pdf(file_path)

    elif file_path.lower().endswith(".docx"):
        return extract_docx(file_path)

    else:
        raise ValueError("Unsupported file type")


def extract_pdf(file_path: str) -> str:
    text = ""

    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()

            if page_text:
                text += page_text + "\n"

    return text


def extract_docx(file_path: str) -> str:
    doc = Document(file_path)

    return "\n".join(
        paragraph.text
        for paragraph in doc.paragraphs
    )