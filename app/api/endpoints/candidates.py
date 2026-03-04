from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
import os, uuid, re, asyncio
from app.core.database import get_db, SessionLocal
from app.core.config import settings
from app.models.job import Job
from app.models.candidate import Candidate
from app.schemas.candidate import CandidateResponse

router = APIRouter()
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}


def _save_file_to_disk(contents: bytes, ext: str) -> str:
    """Save raw file bytes to disk. Returns file path."""
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    file_id   = str(uuid.uuid4())
    file_path = os.path.join(settings.UPLOAD_DIR, f"{file_id}{ext}")
    with open(file_path, "wb") as f:
        f.write(contents)
    return file_path


def _extract_text_sync(file_path: str, ext: str) -> str:
    """
    Synchronous text extraction — runs in a thread so it never blocks FastAPI.
    Only does fast text-layer extraction here.
    Vision OCR (for Canva/scanned PDFs) runs during screening, not upload.
    """
    try:
        if ext == ".pdf":
            # Try PyMuPDF first
            try:
                import fitz
                doc  = fitz.open(file_path)
                text = "".join(page.get_text() for page in doc).strip()
                doc.close()
                if len(text) > 100:
                    return text
            except Exception:
                pass
            # Try pdfplumber
            try:
                import pdfplumber
                with pdfplumber.open(file_path) as pdf:
                    text = "\n".join(p.extract_text() or "" for p in pdf.pages).strip()
                if len(text) > 100:
                    return text
            except Exception:
                pass
            # Text too short — mark for vision OCR during screening
            return "__NEEDS_OCR__"

        elif ext in [".docx", ".doc"]:
            from docx import Document
            doc  = Document(file_path)
            return "\n".join(p.text for p in doc.paragraphs).strip()

    except Exception as e:
        print(f"[Upload] Text extraction error: {e}")

    return ""


def _quick_name_from_filename(filename: str) -> Optional[str]:
    """Extract a readable name from filenames like 01_Arjun_Sharma.pdf"""
    base  = os.path.splitext(os.path.basename(filename))[0]
    parts = re.sub(r'^[\d_]+', '', base).replace('_', ' ').replace('-', ' ').strip()
    return parts.title() if len(parts) > 2 else None


def _quick_regex(text: str, filename: str = "") -> dict:
    """Fast regex pass for basic fields only — runs instantly."""
    if text == "__NEEDS_OCR__":
        text = ""
    email    = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
    phone    = re.findall(r'[\+\(]?[1-9][0-9 .\-\(\)]{8,}[0-9]', text)
    linkedin = re.findall(r'(?:https?://)?(?:www\.)?linkedin\.com/in/([\w\-]+)', text)
    github   = re.findall(r'(?:https?://)?(?:www\.)?github\.com/([\w\-]+)', text)
    kaggle   = re.findall(r'(?:https?://)?(?:www\.)?kaggle\.com/([\w\-]+)', text)
    lines    = [l.strip() for l in text.split('\n') if l.strip()]
    name     = (
        _quick_name_from_filename(filename)
        or (lines[0] if lines and len(lines[0]) < 60 else None)
    )
    return {
        "full_name":    name,
        "email":        email[0]    if email    else None,
        "phone":        phone[0]    if phone    else None,
        "linkedin_url": f"https://linkedin.com/in/{linkedin[0]}" if linkedin else None,
        "github_url":   f"https://github.com/{github[0]}"        if github   else None,
        "kaggle_url":   f"https://kaggle.com/{kaggle[0]}"        if kaggle   else None,
    }


async def _process_single_file(
    job_id: str,
    filename: str,
    contents: bytes,
    ext: str,
    linkedin_url: Optional[str],
    github_url: Optional[str],
    kaggle_url: Optional[str],
    db: Session
) -> Candidate:
    """
    Core upload logic for one file:
    1. Save to disk (instant)
    2. Extract text in background thread (non-blocking)
    3. Quick regex for name/email/links
    4. Save candidate record to DB
    Full LLM extraction + scoring happens later in the LangGraph pipeline.
    """
    # 1. Save file
    file_path = await asyncio.to_thread(_save_file_to_disk, contents, ext)

    # 2. Extract text in thread — doesn't block the event loop
    raw_text  = await asyncio.to_thread(_extract_text_sync, file_path, ext)

    needs_ocr = raw_text == "__NEEDS_OCR__"
    if needs_ocr:
        print(f"[Upload] {filename} — image-based PDF, OCR will run during screening")
        raw_text = ""   # will be filled by vision OCR in LangGraph Node 1

    # 3. Quick regex
    basic = _quick_regex(raw_text, filename)

    # 4. Save to DB
    candidate = Candidate(
        job_id           = job_id,
        full_name        = linkedin_url and basic["full_name"] or basic["full_name"],
        email            = basic["email"],
        phone            = basic["phone"],
        cv_file_path     = file_path,
        cv_raw_text      = raw_text,
        skills           = None,
        experience_years = 0,
        education        = None,
        work_history     = None,
        linkedin_url     = linkedin_url or basic["linkedin_url"],
        github_url       = github_url   or basic["github_url"],
        kaggle_url       = kaggle_url   or basic["kaggle_url"],
        source           = "manual_upload"
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)

    status = "needs OCR" if needs_ocr else f"{len(raw_text)} chars extracted"
    print(f"[Upload] Saved: {basic['full_name'] or filename} — {status}")
    return candidate


# ── ENDPOINTS ────────────────────────────────────────────────────────────────

@router.post("/upload/{job_id}", response_model=CandidateResponse, status_code=201)
async def upload_cv(
    job_id: str,
    file: UploadFile = File(...),
    linkedin_url: Optional[str] = Form(None),
    github_url:   Optional[str] = Form(None),
    kaggle_url:   Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Upload a single CV (PDF or DOCX)."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    contents = await file.read()
    size_mb  = len(contents) / (1024 * 1024)
    if size_mb > settings.MAX_FILE_SIZE_MB:
        raise HTTPException(status_code=400, detail=f"File too large ({size_mb:.1f}MB). Max {settings.MAX_FILE_SIZE_MB}MB.")

    return await _process_single_file(
        job_id, file.filename, contents, ext,
        linkedin_url, github_url, kaggle_url, db
    )


@router.post("/upload-bulk/{job_id}", status_code=201)
async def upload_bulk_cvs(
    job_id: str,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db)
):
    """
    Upload up to 20 CVs at once.
    Files are processed concurrently — heavy files don't block each other.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if len(files) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 files per upload.")

    # Read all file contents first (must be done in async context)
    file_data = []
    for file in files:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            file_data.append((file.filename, None, ext, "Unsupported file type"))
            continue
        contents = await file.read()
        size_mb  = len(contents) / (1024 * 1024)
        if size_mb > settings.MAX_FILE_SIZE_MB:
            file_data.append((file.filename, None, ext, f"File too large ({size_mb:.1f}MB)"))
            continue
        file_data.append((file.filename, contents, ext, None))

    # Process all files concurrently
    async def process_one(filename, contents, ext, pre_error):
        if pre_error:
            return {"filename": filename, "status": "failed", "error": pre_error}
        try:
            candidate = await _process_single_file(
                job_id, filename, contents, ext,
                None, None, None, db
            )
            return {
                "filename":       filename,
                "status":         "success",
                "candidate_id":   candidate.id,
                "name_extracted": candidate.full_name or "Will extract during screening"
            }
        except Exception as e:
            return {"filename": filename, "status": "failed", "error": str(e)}

    all_results = await asyncio.gather(*[
        process_one(fn, ct, ex, err) for fn, ct, ex, err in file_data
    ])

    results = [r for r in all_results if r["status"] == "success"]
    errors  = [r for r in all_results if r["status"] == "failed"]

    return {
        "job_id":         job_id,
        "total_uploaded": len(files),
        "successful":     len(results),
        "failed":         len(errors),
        "results":        results,
        "errors":         errors,
        "message":        "CVs saved. Run screening to score all candidates."
    }


@router.get("/{job_id}", response_model=List[CandidateResponse])
async def list_candidates(job_id: str, db: Session = Depends(get_db)):
    """List all candidates for a job."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return db.query(Candidate).filter(Candidate.job_id == job_id).all()


@router.get("/candidate/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(candidate_id: str, db: Session = Depends(get_db)):
    """Get a specific candidate's full profile."""
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


@router.delete("/candidate/{candidate_id}", status_code=204)
async def delete_candidate(candidate_id: str, db: Session = Depends(get_db)):
    """Remove a candidate."""
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if candidate.cv_file_path and os.path.exists(candidate.cv_file_path):
        os.remove(candidate.cv_file_path)
    db.delete(candidate)
    db.commit()
