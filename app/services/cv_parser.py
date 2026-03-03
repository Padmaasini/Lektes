import re
import base64
from app.core.config import settings


def extract_text(file_path: str, ext: str) -> str:
    """
    Extract raw text from a CV file.
    Tries text-based extraction first (fast).
    Falls back to OCR via Groq vision if text is too short (image-based / Canva PDFs).
    """
    try:
        if ext == ".pdf":
            return extract_from_pdf(file_path)
        elif ext in [".docx", ".doc"]:
            return extract_from_docx(file_path)
        return ""
    except Exception as e:
        print(f"[CV Parser] Extraction error: {e}")
        return ""


def extract_from_pdf(file_path: str) -> str:
    """
    PDF text extraction with OCR fallback.

    Strategy:
      1. PyMuPDF  — fast, works for most text-based PDFs
      2. pdfplumber — second attempt for tricky text layouts
      3. Groq vision OCR — fallback for image-based PDFs (Canva, scanned, etc.)
    """
    text = ""

    # Attempt 1 — PyMuPDF
    try:
        import fitz
        doc  = fitz.open(file_path)
        text = "".join(page.get_text() for page in doc).strip()
        doc.close()
        print(f"[CV Parser] PyMuPDF extracted {len(text)} chars")
    except Exception as e:
        print(f"[CV Parser] PyMuPDF failed: {e}")

    # Attempt 2 — pdfplumber (if PyMuPDF got too little)
    if len(text) < 100:
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                text = "\n".join(
                    page.extract_text() or "" for page in pdf.pages
                ).strip()
            print(f"[CV Parser] pdfplumber extracted {len(text)} chars")
        except Exception as e:
            print(f"[CV Parser] pdfplumber failed: {e}")

    # Attempt 3 — Groq Vision OCR (Canva / scanned / image-based PDFs)
    if len(text) < 100:
        print(f"[CV Parser] Text too short ({len(text)} chars) — attempting vision OCR")
        text = extract_with_vision_ocr(file_path)

    return text


def extract_with_vision_ocr(file_path: str) -> str:
    """
    Renders PDF pages as images and sends them to Groq's vision model
    to extract text. Handles Canva CVs, scanned PDFs, image-based PDFs.
    Uses llama-3.2-11b-vision-preview — free on Groq.
    """
    try:
        import fitz  # PyMuPDF
        from groq import Groq

        client = Groq(api_key=settings.GROQ_API_KEY)
        doc    = fitz.open(file_path)
        all_text = []

        for page_num, page in enumerate(doc):
            # Render page as PNG image at 2x resolution for better OCR
            mat    = fitz.Matrix(2.0, 2.0)
            pix    = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")
            img_b64   = base64.standard_b64encode(img_bytes).decode("utf-8")

            print(f"[CV Parser] Vision OCR — page {page_num + 1}/{len(doc)}")

            response = client.chat.completions.create(
                model="llama-3.2-11b-vision-preview",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{img_b64}"
                                }
                            },
                            {
                                "type": "text",
                                "text": (
                                    "This is a page from a CV/resume. "
                                    "Extract ALL text exactly as it appears — "
                                    "name, contact info, skills, experience, education, "
                                    "everything. Return only the extracted text, no commentary."
                                )
                            }
                        ]
                    }
                ],
                max_tokens=2048,
            )
            page_text = response.choices[0].message.content.strip()
            all_text.append(page_text)
            print(f"[CV Parser] Vision OCR page {page_num + 1}: {len(page_text)} chars extracted")

        doc.close()
        result = "\n\n".join(all_text)
        print(f"[CV Parser] Vision OCR total: {len(result)} chars")
        return result

    except Exception as e:
        print(f"[CV Parser] Vision OCR failed: {e}")
        return ""


def extract_from_docx(file_path: str) -> str:
    """Extract text from Word documents."""
    try:
        from docx import Document
        doc  = Document(file_path)
        text = "\n".join(para.text for para in doc.paragraphs).strip()
        print(f"[CV Parser] DOCX extracted {len(text)} chars")
        return text
    except Exception as e:
        print(f"[CV Parser] DOCX extraction error: {e}")
        return ""


async def parse_cv(file_path: str, ext: str) -> dict:
    """
    Legacy function kept for compatibility.
    Full extraction now happens during screening via LangGraph Node 1.
    This just returns raw text + basic regex fields.
    """
    raw_text = extract_text(file_path, ext)
    print(f"[CV Parser] Total extracted: {len(raw_text)} chars from {ext}")

    if not raw_text:
        print("[CV Parser] WARNING: No text extracted — CV may be unreadable")
        return get_empty_structure()

    basic = extract_with_regex(raw_text, file_path)
    basic["raw_text"] = raw_text
    return basic


def extract_with_regex(text: str, file_path: str = "") -> dict:
    """Fast regex extraction for basic fields during upload."""
    email    = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
    phone    = re.findall(r'[\+\(]?[1-9][0-9 .\-\(\)]{8,}[0-9]', text)
    linkedin = re.findall(r'linkedin\.com/in/[\w\-]+', text)
    github   = re.findall(r'github\.com/[\w\-]+', text)
    kaggle   = re.findall(r'kaggle\.com/[\w\-]+', text)

    # Try to get name from filename first
    import os
    name = None
    if file_path:
        base  = os.path.splitext(os.path.basename(file_path))[0]
        parts = re.sub(r'^[\d_]+', '', base).replace('_', ' ').replace('-', ' ').strip()
        if len(parts) > 2:
            name = parts.title()

    # Fallback to first short line in text
    if not name:
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        name  = lines[0] if lines and len(lines[0]) < 60 else None

    return {
        "full_name":    name,
        "email":        email[0] if email else None,
        "phone":        phone[0] if phone else None,
        "location":     None,
        "skills":       "",
        "experience_years": 0,
        "education":    None,
        "work_history": None,
        "linkedin_url": f"https://{linkedin[0]}" if linkedin else None,
        "github_url":   f"https://{github[0]}" if github else None,
        "kaggle_url":   f"https://{kaggle[0]}" if kaggle else None,
    }


def get_empty_structure() -> dict:
    return {
        "full_name": None, "email": None, "phone": None,
        "location": None, "skills": "", "experience_years": 0,
        "education": None, "work_history": None, "raw_text": "",
        "linkedin_url": None, "github_url": None, "kaggle_url": None
    }
