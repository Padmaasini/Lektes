import re
import json
from typing import Optional
from app.core.config import settings

async def parse_cv(file_path: str, ext: str) -> dict:
    """
    Parse a CV file and extract structured information.
    Uses PyMuPDF for PDFs, python-docx for Word documents.
    Then uses LLM to extract structured fields.
    """
    raw_text = extract_text(file_path, ext)
    structured = await extract_with_llm(raw_text)
    structured["raw_text"] = raw_text
    return structured

def extract_text(file_path: str, ext: str) -> str:
    """Extract raw text from PDF or DOCX."""
    try:
        if ext == ".pdf":
            return extract_from_pdf(file_path)
        elif ext in [".docx", ".doc"]:
            return extract_from_docx(file_path)
        else:
            return ""
    except Exception as e:
        print(f"Error extracting text: {e}")
        return ""

def extract_from_pdf(file_path: str) -> str:
    """Extract text from PDF using PyMuPDF."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text.strip()
    except ImportError:
        # Fallback to pdfplumber if PyMuPDF not available
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                return "\n".join(
                    page.extract_text() or "" for page in pdf.pages
                ).strip()
        except Exception as e:
            print(f"PDF extraction error: {e}")
            return ""

def extract_from_docx(file_path: str) -> str:
    """Extract text from DOCX using python-docx."""
    try:
        from docx import Document
        doc = Document(file_path)
        return "\n".join(para.text for para in doc.paragraphs).strip()
    except Exception as e:
        print(f"DOCX extraction error: {e}")
        return ""

async def extract_with_llm(raw_text: str) -> dict:
    """
    Use LLM to extract structured fields from raw CV text.
    Falls back to regex if LLM is unavailable.
    """
    if not raw_text:
        return get_empty_structure()

    try:
        from app.services.llm_service import get_llm_response
        prompt = f"""
        Extract the following information from this CV/Resume text and return ONLY a valid JSON object.
        
        CV Text:
        {raw_text[:3000]}
        
        Extract and return this exact JSON structure:
        {{
            "full_name": "candidate full name or null",
            "email": "email address or null",
            "phone": "phone number or null",
            "location": "city/country or null",
            "skills": "comma separated list of technical skills",
            "experience_years": 0,
            "education": "highest degree and institution or null",
            "work_history": "summary of work history",
            "linkedin_url": "linkedin profile URL or null",
            "github_url": "github profile URL or null",
            "kaggle_url": "kaggle profile URL or null"
        }}
        
        Return ONLY the JSON. No explanation, no markdown.
        """
        response = await get_llm_response(prompt)
        # Clean response and parse JSON
        clean = response.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(clean)

    except Exception as e:
        print(f"LLM extraction failed, using regex fallback: {e}")
        return extract_with_regex(raw_text)

def extract_with_regex(text: str) -> dict:
    """Regex fallback for basic field extraction."""
    email = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
    phone = re.findall(r'[\+\(]?[1-9][0-9 .\-\(\)]{8,}[0-9]', text)
    linkedin = re.findall(r'linkedin\.com/in/[\w\-]+', text)
    github = re.findall(r'github\.com/[\w\-]+', text)

    return {
        "full_name": None,
        "email": email[0] if email else None,
        "phone": phone[0] if phone else None,
        "location": None,
        "skills": "",
        "experience_years": 0,
        "education": None,
        "work_history": None,
        "linkedin_url": f"https://{linkedin[0]}" if linkedin else None,
        "github_url": f"https://{github[0]}" if github else None,
        "kaggle_url": None
    }

def get_empty_structure() -> dict:
    return {
        "full_name": None, "email": None, "phone": None,
        "location": None, "skills": "", "experience_years": 0,
        "education": None, "work_history": None,
        "linkedin_url": None, "github_url": None, "kaggle_url": None
    }
