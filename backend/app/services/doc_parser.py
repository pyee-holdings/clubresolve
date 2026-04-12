"""Document parsing service — PDF, DOCX, email extraction with source traceability."""

import email
from email import policy as email_policy
from pathlib import Path

from pypdf import PdfReader


def parse_pdf(file_path: str) -> list[dict]:
    """Extract text from PDF with page-level source tracking.

    Returns list of {"content": "...", "source": "filename.pdf", "page": N}
    """
    path = Path(file_path)
    reader = PdfReader(path)
    chunks = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text and text.strip():
            chunks.append({
                "content": text.strip(),
                "source": path.name,
                "page": i + 1,
                "metadata": {"type": "pdf", "total_pages": len(reader.pages)},
            })
    return chunks


def parse_docx(file_path: str) -> list[dict]:
    """Extract text from DOCX with paragraph-level tracking.

    Returns list of {"content": "...", "source": "filename.docx", "section": N}
    """
    from docx import Document

    path = Path(file_path)
    doc = Document(path)
    chunks = []
    current_section = []
    section_num = 1

    for para in doc.paragraphs:
        if not para.text.strip():
            if current_section:
                chunks.append({
                    "content": "\n".join(current_section),
                    "source": path.name,
                    "section": section_num,
                    "metadata": {"type": "docx"},
                })
                current_section = []
                section_num += 1
        else:
            current_section.append(para.text.strip())

    # Don't forget the last section
    if current_section:
        chunks.append({
            "content": "\n".join(current_section),
            "source": path.name,
            "section": section_num,
            "metadata": {"type": "docx"},
        })

    return chunks


def parse_email_file(file_path: str) -> dict:
    """Extract structured data from an email (.eml) file.

    Returns {"subject": "...", "from": "...", "to": "...", "date": "...", "body": "...", "source": "filename.eml"}
    """
    path = Path(file_path)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        msg = email.message_from_file(f, policy=email_policy.default)

    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                body = part.get_content()
                break
    else:
        body = msg.get_content()

    return {
        "subject": str(msg.get("Subject", "")),
        "from": str(msg.get("From", "")),
        "to": str(msg.get("To", "")),
        "date": str(msg.get("Date", "")),
        "body": body.strip() if isinstance(body, str) else "",
        "source": path.name,
        "metadata": {"type": "email"},
    }


def parse_document(file_path: str) -> list[dict]:
    """Auto-detect file type and parse accordingly."""
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return parse_pdf(file_path)
    elif suffix in (".docx", ".doc"):
        return parse_docx(file_path)
    elif suffix == ".eml":
        result = parse_email_file(file_path)
        return [{"content": f"Subject: {result['subject']}\nFrom: {result['from']}\nDate: {result['date']}\n\n{result['body']}", **{k: v for k, v in result.items() if k != 'body'}}]
    elif suffix in (".txt", ".md"):
        text = path.read_text(encoding="utf-8", errors="replace")
        return [{"content": text, "source": path.name, "metadata": {"type": "text"}}]
    else:
        raise ValueError(f"Unsupported file type: {suffix}")
