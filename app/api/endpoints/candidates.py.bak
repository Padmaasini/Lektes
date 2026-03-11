from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
import os, shutil, uuid
from app.core.database import get_db
from app.core.config import settings
from app.models.job import Job
from app.models.candidate import Candidate
from app.schemas.candidate import CandidateResponse
from app.services.cv_parser import parse_cv

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}

@router.post("/upload/{job_id}", response_model=CandidateResponse, status_code=201)
async def upload_cv(
    job_id: str,
    file: UploadFile = File(...),
    linkedin_url: Optional[str] = Form(None),
    github_url: Optional[str] = Form(None),
    kaggle_url: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Upload a CV for a specific job.
    Accepts PDF or DOCX files.
    Optionally include LinkedIn, GitHub, and Kaggle URLs.
    """
    # Validate job exists
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Validate file type
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported. Please upload PDF or DOCX. Got: {ext}"
        )

    # Validate file size
    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > settings.MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Max size is {settings.MAX_FILE_SIZE_MB}MB. Got {size_mb:.1f}MB"
        )

    # Save file
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    file_id = str(uuid.uuid4())
    file_path = os.path.join(settings.UPLOAD_DIR, f"{file_id}{ext}")

    with open(file_path, "wb") as f:
        f.write(contents)

    # Parse CV
    parsed = await parse_cv(file_path, ext)

    # Create candidate record
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
        source="manual_upload"
    )

    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate

@router.get("/{job_id}", response_model=List[CandidateResponse])
async def list_candidates(job_id: str, db: Session = Depends(get_db)):
    """List all candidates for a job."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return db.query(Candidate).filter(Candidate.job_id == job_id).all()

@router.get("/candidate/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(candidate_id: str, db: Session = Depends(get_db)):
    """Get a specific candidate's full profile and score."""
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate

@router.delete("/candidate/{candidate_id}", status_code=204)
async def delete_candidate(candidate_id: str, db: Session = Depends(get_db)):
    """Remove a candidate from the screening pool."""
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if candidate.cv_file_path and os.path.exists(candidate.cv_file_path):
        os.remove(candidate.cv_file_path)
    db.delete(candidate)
    db.commit()
