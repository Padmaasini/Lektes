from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.job import Job
from app.schemas.job import JobCreate, JobResponse

router = APIRouter()

@router.post("/", response_model=JobResponse, status_code=201)
async def create_job(job: JobCreate, db: Session = Depends(get_db)):
    """
    Create a new job screening session.
    This is your starting point — every candidate is linked to a job.
    """
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
    """List all active job screening sessions."""
    return db.query(Job).all()

@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, db: Session = Depends(get_db)):
    """Get a specific job by ID."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.delete("/{job_id}", status_code=204)
async def delete_job(job_id: str, db: Session = Depends(get_db)):
    """Delete a job and all associated candidates."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    db.delete(job)
    db.commit()
