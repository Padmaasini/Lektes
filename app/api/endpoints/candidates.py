"""
Candidates endpoints — upload, list, retrieve, erase.

GDPR additions:
  - consent_given required on every upload (blocks if False)
  - expires_at set automatically to DATA_RETENTION_DAYS from now
  - DELETE /erase/{id} is the right-to-erasure endpoint (GDPR Art. 17)
    deletes CV file from disk + all DB records for this candidate

Security:
  - All write endpoints protected by require_api_key
  - File type whitelist enforced
  - File size limit enforced
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
import os, uuid

from app.core.database import get_db
from app.core.config import settings
from app.core.security import require_api_key
from app.models.job import Job
from app.models.candidate import Candidate
from app.schemas.candidate import CandidateResponse
from app.services.cv_parser import parse_cv

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}


def _set_expiry() -> datetime:
    return datetime.utcnow() + timedelta(days=settings.DATA_RETENTION_DAYS)


def _delete_cv_file(path: Optional[str]) -> None:
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


# ── UPLOAD ───────────────────────────────────────────────────

@router.post("/upload/{job_id}", response_model=CandidateResponse, status_code=201)
async def upload_cv(
    job_id:        str,
    file:          UploadFile    = File(...),
    consent_given: bool          = Form(..., description="HR confirms candidate consented to AI processing"),
    linkedin_url:  Optional[str] = Form(None),
    github_url:    Optional[str] = Form(None),
    kaggle_url:    Optional[str] = Form(None),
    db:            Session       = Depends(get_db),
    _:             None          = Depends(require_api_key),
):
    """Upload a single CV. consent_given=true is required (GDPR)."""
    if not consent_given:
        raise HTTPException(
            status_code=422,
            detail="Candidate consent required before uploading CV."
        )

    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported type '{ext}'. Upload PDF or DOCX.")

    contents = await file.read()
    size_mb  = len(contents) / (1024 * 1024)
    if size_mb > settings.MAX_FILE_SIZE_MB:
        raise HTTPException(status_code=400, detail=f"File too large ({size_mb:.1f} MB). Max {settings.MAX_FILE_SIZE_MB} MB.")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(settings.UPLOAD_DIR, f"{uuid.uuid4()}{ext}")
    with open(file_path, "wb") as f:
        f.write(contents)

    parsed = await parse_cv(file_path, ext)

    candidate = Candidate(
        job_id=job_id,
        full_name=parsed.get("full_name"),
        email=parsed.get("email"),
        phone=parsed.get("phone"),
        location=parsed.get("location"),
        cv_file_path=file_path,
        cv_raw_text=parsed.get("raw_text"),
        skills=parsed.get("skills"),
        experience_years=parsed.get("experience_years", 0),
        education=parsed.get("education"),
        work_history=parsed.get("work_history"),
        linkedin_url=linkedin_url or parsed.get("linkedin_url"),
        github_url=github_url or parsed.get("github_url"),
        kaggle_url=kaggle_url or parsed.get("kaggle_url"),
        source="manual_upload",
        consent_given=True,
        expires_at=_set_expiry(),
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate


@router.post("/upload-bulk/{job_id}", status_code=201)
async def upload_bulk_cvs(
    job_id:        str,
    files:         List[UploadFile] = File(...),
    consent_given: bool             = Form(..., description="HR confirms all candidates consented"),
    db:            Session          = Depends(get_db),
    _:             None             = Depends(require_api_key),
):
    """Upload up to 20 CVs at once. consent_given applies to all files."""
    if not consent_given:
        raise HTTPException(status_code=422, detail="Candidate consent required for all uploaded CVs.")

    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if len(files) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 files per batch upload.")

    results, errors = [], []

    for file in files:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            errors.append({"filename": file.filename, "error": f"Unsupported type: {ext}"}); continue
        contents = await file.read()
        size_mb  = len(contents) / (1024 * 1024)
        if size_mb > settings.MAX_FILE_SIZE_MB:
            errors.append({"filename": file.filename, "error": f"Too large ({size_mb:.1f} MB)"}); continue
        try:
            os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
            file_path = os.path.join(settings.UPLOAD_DIR, f"{uuid.uuid4()}{ext}")
            with open(file_path, "wb") as f:
                f.write(contents)
            parsed    = await parse_cv(file_path, ext)
            candidate = Candidate(
                job_id=job_id, full_name=parsed.get("full_name"),
                email=parsed.get("email"), phone=parsed.get("phone"),
                location=parsed.get("location"), cv_file_path=file_path,
                cv_raw_text=parsed.get("raw_text"), skills=parsed.get("skills"),
                experience_years=parsed.get("experience_years", 0),
                education=parsed.get("education"), work_history=parsed.get("work_history"),
                linkedin_url=parsed.get("linkedin_url"), github_url=parsed.get("github_url"),
                kaggle_url=parsed.get("kaggle_url"), source="manual_upload",
                consent_given=True, expires_at=_set_expiry(),
            )
            db.add(candidate); db.commit(); db.refresh(candidate)
            results.append({"filename": file.filename, "status": "success",
                            "candidate_id": candidate.id, "name": candidate.full_name or "Extracting…"})
        except Exception as e:
            errors.append({"filename": file.filename, "error": str(e)})

    return {"job_id": job_id, "successful": len(results), "failed": len(errors),
            "results": results, "errors": errors,
            "message": "CVs uploaded. Run screening to score candidates."}


# ── READ ─────────────────────────────────────────────────────

@router.get("/{job_id}", response_model=List[CandidateResponse])
async def list_candidates(job_id: str, db: Session = Depends(get_db),
                          _: None = Depends(require_api_key)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return db.query(Candidate).filter(Candidate.job_id == job_id).all()


@router.get("/candidate/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(candidate_id: str, db: Session = Depends(get_db),
                        _: None = Depends(require_api_key)):
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


# ── DELETE ────────────────────────────────────────────────────

@router.delete("/candidate/{candidate_id}", status_code=204)
async def delete_candidate(candidate_id: str, db: Session = Depends(get_db),
                           _: None = Depends(require_api_key)):
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    _delete_cv_file(candidate.cv_file_path)
    db.delete(candidate)
    db.commit()


@router.delete("/erase/{candidate_id}", status_code=200)
async def erase_candidate(candidate_id: str, db: Session = Depends(get_db),
                          _: None = Depends(require_api_key)):
    """
    GDPR Article 17 — Right to Erasure.
    Permanently deletes CV file + all DB records including feedback.
    Call this when a candidate requests deletion of their personal data.
    """
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    name   = candidate.full_name or candidate_id
    job_id = candidate.job_id

    _delete_cv_file(candidate.cv_file_path)
    candidate.cv_raw_text  = None
    candidate.cv_file_path = None
    db.commit()
    db.delete(candidate)
    db.commit()

    return {
        "message":      f"All data for '{name}' permanently erased.",
        "candidate_id": candidate_id,
        "job_id":       job_id,
        "gdpr":         "Right to erasure fulfilled (GDPR Art. 17)",
    }
