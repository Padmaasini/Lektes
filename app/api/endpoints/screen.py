from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime
from app.core.database import get_db
from app.models.job import Job
from app.models.candidate import Candidate
from app.models.screening import Screening
from app.services.screening_pipeline import run_screening_pipeline

router = APIRouter()

@router.post("/{job_id}", status_code=202)
async def trigger_screening(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Trigger the full AI screening pipeline for a job.
    This runs asynchronously in the background.
    Returns immediately with a screening_id to track progress.
    """
    # Validate job
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Check candidates exist
    candidate_count = db.query(Candidate).filter(Candidate.job_id == job_id).count()
    if candidate_count == 0:
        raise HTTPException(
            status_code=400,
            detail="No candidates found for this job. Upload CVs first."
        )

    # Create screening record
    screening = Screening(job_id=job_id, status="pending")
    db.add(screening)
    job.status = "screening"
    db.commit()
    db.refresh(screening)

    # Run pipeline in background
    background_tasks.add_task(run_screening_pipeline, job_id, screening.id)

    return {
        "message": "Screening pipeline triggered successfully",
        "screening_id": screening.id,
        "job_id": job_id,
        "candidates_to_screen": candidate_count,
        "status": "pending",
        "check_status": f"/api/v1/screen/status/{screening.id}"
    }

@router.get("/status/{screening_id}")
async def get_screening_status(screening_id: str, db: Session = Depends(get_db)):
    """
    Check the status of a running screening pipeline.
    Poll this endpoint until status is 'completed' or 'failed'.
    """
    screening = db.query(Screening).filter(Screening.id == screening_id).first()
    if not screening:
        raise HTTPException(status_code=404, detail="Screening not found")

    # Count how many candidates have been scored so far (live progress)
    total_count  = db.query(Candidate).filter(Candidate.job_id == screening.job_id).count()
    scored_count = db.query(Candidate).filter(
        Candidate.job_id == screening.job_id,
        Candidate.match_score.isnot(None)
    ).count()

    response = {
        "screening_id": screening.id,
        "job_id":       screening.job_id,
        "status":       screening.status,
        "report_ready": screening.status == "completed",
        "scored_count": scored_count,
        "total_count":  total_count,
        "created_at":   screening.created_at.isoformat(),
    }

    if screening.completed_at:
        response["completed_at"] = screening.completed_at.isoformat()

    if screening.status == "completed":
        response["report_url"] = f"/api/v1/reports/{screening.job_id}"

    if screening.status == "failed":
        response["error"] = screening.error_message

    return response
