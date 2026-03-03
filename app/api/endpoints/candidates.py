from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
import os, uuid, re
from app.core.database import get_db
from app.core.config import settings
from app.models.job import Job
from app.models.candidate import Candidate
from app.schemas.candidate import CandidateResponse
from app.services.cv_parser import extract_text

router = APIRouter()
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}

def quick_extract(raw_text: str, filename: str = "") -> dict:
    """
    Fast regex extraction — no LLM calls.
    Extracts only what regex can reliably find.
    LLM extraction happens later during screening.
    """
    email   = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', raw_text)
    phone   = re.findall(r'[\+\(]?[1-9][0-9 .\-\(\)]{8,}[0-9]', raw_text)
    linkedin = re.findall(r'(?:https?://)?(?:www\.)?linkedin\.com/in/([\w\-]+)', raw_text)
    github   = re.findall(r'(?:https?://)?(?:www\.)?github\.com/([\w\-]+)', raw_text)
    kaggle   = re.findall(r'(?:https?://)?(?:www\.)?kaggle\.com/([\w\-]+)', raw_text)

    # Try to get name from filename (e.g. "01_Arjun_Sharma.pdf" → "Arjun Sharma")
    name_from_file = None
    if filename:
        base = os.path.splitext(os.path.basename(filename))[0]
        parts = re.sub(r'^[\d_]+', '', base).replace('_', ' ').replace('-', ' ').strip()
        if len(parts) > 2:
            name_from_file = parts.title()

    # Try first non-empty line as name fallback
    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
    name_from_text = lines[0] if lines and len(lines[0]) < 60 else None

    return {
        "full_name": name_from_file or name_from_text,
        "email":     email[0] if email else None,
        "phone":     phone[0] if phone else None,
        "linkedin_url": f"https://linkedin.com/in/{linkedin[0]}" if linkedin else None,
        "github_url":   f"https://github.com/{github[0]}" if github else None,
        "kaggle_url":   f"https://kaggle.com/{kaggle[0]}" if kaggle else None,
    }

async def _save_cv(job_id, file, linkedin_url, github_url, kaggle_url, db):
    """
    Save CV file and extract raw text only.
    No LLM call here — LLM extraction happens during screening.
    """
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}. Use PDF or DOCX.")

    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > settings.MAX_FILE_SIZE_MB:
        raise HTTPException(status_code=400, detail=f"File too large ({size_mb:.1f}MB). Max {settings.MAX_FILE_SIZE_MB}MB.")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    file_id  = str(uuid.uuid4())
    file_path = os.path.join(settings.UPLOAD_DIR, f"{file_id}{ext}")

    with open(file_path, "wb") as f:
        f.write(contents)

    # Extract raw text only — fast, no LLM
    raw_text = extract_text(file_path, ext)

    # Quick regex extraction for basic fields
    basic = quick_extract(raw_text, file.filename)

    candidate = Candidate(
        job_id       = job_id,
        full_name    = linkedin_url and basic["full_name"] or basic["full_name"],
        email        = basic["email"],
        phone        = basic["phone"],
        cv_file_path = file_path,
        cv_raw_text  = raw_text,
        # Skills, education, work_history left null — filled by LLM during screening
        skills           = None,
        experience_years = 0,
        education        = None,
        work_history     = None,
        linkedin_url = linkedin_url or basic["linkedin_url"],
        github_url   = github_url   or basic["github_url"],
        kaggle_url   = kaggle_url   or basic["kaggle_url"],
        source       = "manual_upload"
    )

    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate


@router.post("/upload/{job_id}", response_model=CandidateResponse, status_code=201)
async def upload_cv(
    job_id: str,
    file: UploadFile = File(...),
    linkedin_url: Optional[str] = Form(None),
    github_url:   Optional[str] = Form(None),
    kaggle_url:   Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Upload a single CV (PDF or DOCX) for a job."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return await _save_cv(job_id, file, linkedin_url, github_url, kaggle_url, db)


@router.post("/upload-bulk/{job_id}", status_code=201)
async def upload_bulk_cvs(
    job_id: str,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db)
):
    """Upload up to 20 CVs at once. Fast — no LLM during upload."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if len(files) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 files per bulk upload.")

    results, errors = [], []
    for file in files:
        try:
            candidate = await _save_cv(job_id, file, None, None, None, db)
            results.append({
                "filename":       file.filename,
                "status":         "success",
                "candidate_id":   candidate.id,
                "name_extracted": candidate.full_name or "Will extract during screening"
            })
        except Exception as e:
            errors.append({"filename": file.filename, "status": "failed", "error": str(e)})

    return {
        "job_id":          job_id,
        "total_uploaded":  len(files),
        "successful":      len(results),
        "failed":          len(errors),
        "results":         results,
        "errors":          errors,
        "message":         "CVs saved. Trigger screening to extract skills and score candidates."
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
