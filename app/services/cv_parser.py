import re
import json
from app.core.config import settings

async def parse_cv(file_path: str, ext: str) -> dict:
    raw_text = extract_text(file_path, ext)
    print(f"[CV Parser] Extracted {len(raw_text)} characters from {ext} file")
    if not raw_text:
        print("[CV Parser] WARNING: No text extracted from file")
        return get_empty_structure()
    structured = await extract_with_llm(raw_text)
    structured["raw_text"] = raw_text
    return structured

def extract_text(file_path: str, ext: str) -> str:
    try:
        if ext == ".pdf":
            return extract_from_pdf(file_path)
        elif ext in [".docx", ".doc"]:
            return extract_from_docx(file_path)
        return ""
    except Exception as e:
        print(f"[CV Parser] Error extracting text: {e}")
        return ""

def extract_from_pdf(file_path: str) -> str:
    try:
        import fitz
        doc = fitz.open(file_path)
        text = "".join(page.get_text() for page in doc)
        doc.close()
        return text.strip()
    except Exception as e:
        print(f"[CV Parser] PyMuPDF failed: {e}, trying pdfplumber")
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                return "\n".join(page.extract_text() or "" for page in pdf.pages).strip()
        except Exception as e2:
            print(f"[CV Parser] pdfplumber also failed: {e2}")
            return ""

def extract_from_docx(file_path: str) -> str:
    try:
        from docx import Document
        doc = Document(file_path)
        return "\n".join(para.text for para in doc.paragraphs).strip()
    except Exception as e:
        print(f"[CV Parser] DOCX extraction error: {e}")
        return ""

async def extract_with_llm(raw_text: str) -> dict:
    if not settings.GEMINI_API_KEY:
        print("[CV Parser] WARNING: GEMINI_API_KEY not set — using regex fallback")
        return extract_with_regex(raw_text)
    try:
        from app.services.llm_service import get_llm_response
        prompt = f"""You are a CV parsing assistant. Extract information from the CV below.
Return ONLY a valid JSON object with no markdown, no backticks, no explanation.

CV TEXT:
{raw_text[:4000]}

Return this exact JSON structure (use null for missing fields):
{{
    "full_name": "candidate full name",
    "email": "email address",
    "phone": "phone number",
    "location": "city and country",
    "skills": "comma separated list of ALL technical skills",
    "experience_years": 3,
    "education": "highest degree, field, and university",
    "work_history": "brief 2-3 sentence summary of work history",
    "linkedin_url": "full linkedin URL if present else null",
    "github_url": "full github URL if present else null",
    "kaggle_url": "full kaggle URL if present else null"
}}

IMPORTANT: experience_years must be an integer. skills must be comma-separated string. Return ONLY JSON.
"""
        print("[CV Parser] Calling Gemini API...")
        response = await get_llm_response(prompt)
        print(f"[CV Parser] Gemini responded ({len(response)} chars)")
        clean = response.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()
        parsed = json.loads(clean)
        try:
            parsed["experience_years"] = int(parsed.get("experience_years") or 0)
        except (ValueError, TypeError):
            parsed["experience_years"] = 0
        print(f"[CV Parser] Parsed: name={parsed.get('full_name')}")
        return parsed
    except Exception as e:
        print(f"[CV Parser] Gemini failed: {e} — using regex fallback")
        return extract_with_regex(raw_text)

def extract_with_regex(text: str) -> dict:
    print("[CV Parser] Running regex extraction")
    email = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
    phone = re.findall(r'[\+\(]?[1-9][0-9 .\-\(\)]{8,}[0-9]', text)
    linkedin = re.findall(r'linkedin\.com/in/[\w\-]+', text)
    github = re.findall(r'github\.com/[\w\-]+', text)
    kaggle = re.findall(r'kaggle\.com/[\w\-]+', text)
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    name = lines[0] if lines and len(lines[0]) < 60 else None
    tech_kw = ["Python","FastAPI","Django","Flask","SQL","PostgreSQL","MySQL","MongoDB",
               "Docker","Kubernetes","AWS","Azure","React","JavaScript","TypeScript",
               "Node.js","Java","Go","Machine Learning","TensorFlow","PyTorch","Pandas","Git"]
    found_skills = [kw for kw in tech_kw if kw.lower() in text.lower()]
    return {
        "full_name": name,
        "email": email[0] if email else None,
        "phone": phone[0] if phone else None,
        "location": None,
        "skills": ", ".join(found_skills) if found_skills else "",
        "experience_years": 0,
        "education": None,
        "work_history": None,
        "linkedin_url": f"https://{linkedin[0]}" if linkedin else None,
        "github_url": f"https://{github[0]}" if github else None,
        "kaggle_url": f"https://{kaggle[0]}" if kaggle else None
    }

def get_empty_structure() -> dict:
    return {
        "full_name": None, "email": None, "phone": None,
        "location": None, "skills": "", "experience_years": 0,
        "education": None, "work_history": None,
        "linkedin_url": None, "github_url": None, "kaggle_url": None
    }
