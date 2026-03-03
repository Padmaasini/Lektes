from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.job import Job
from app.models.candidate import Candidate
from app.schemas.job import JobCreate, JobResponse

router = APIRouter()

@router.post("/", response_model=JobResponse, status_code=201)
async def create_job(job: JobCreate, db: Session = Depends(get_db)):
    """Create a new job screening session."""
    db_job = Job(
        title=job.title,
        description=job.description,
        required_skills=",".join(job.required_skills) if job.required_skills else "",
        nice_to_have_skills=",".join(job.nice_to_have_skills) if job.nice_to_have_skills else "",
        min_experience_years=job.min_experience_years,
        hr_email=job.hr_email
    )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    return db_job

@router.get("/", response_model=List[JobResponse])
async def list_jobs(db: Session = Depends(get_db)):
    """List all job screening sessions."""
    return db.query(Job).order_by(Job.created_at.desc()).all()

@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, db: Session = Depends(get_db)):
    """Get a specific job by ID."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.delete("/{job_id}", status_code=204)
async def delete_job(job_id: str, db: Session = Depends(get_db)):
    """Delete a job and all its candidates."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    db.delete(job)
    db.commit()

@router.delete("/", status_code=200)
async def delete_all_jobs(db: Session = Depends(get_db)):
    """Delete ALL jobs and candidates — full database reset."""
    candidate_count = db.query(Candidate).count()
    job_count = db.query(Job).count()
    db.query(Candidate).delete()
    db.query(Job).delete()
    db.commit()
    return {
        "message": "All data cleared successfully",
        "jobs_deleted": job_count,
        "candidates_deleted": candidate_count
    }
