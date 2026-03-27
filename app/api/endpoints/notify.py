"""
Lektes Candidate Notification Endpoint
POST /api/v1/notify/shortlist/{candidate_id}  — send interview invitation
POST /api/v1/notify/reject/{candidate_id}     — send rejection email
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.security import require_api_key
from app.models.candidate import Candidate
from app.models.job import Job

router = APIRouter()


class NotifyRequest(BaseModel):
    hr_name:       Optional[str] = "The Hiring Team"
    calendly_link: Optional[str] = None


@router.post("/shortlist/{candidate_id}")
async def notify_shortlist(
    candidate_id: str,
    body: NotifyRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key),
):
    """Send interview invitation email to a shortlisted candidate."""
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if not candidate.email:
        raise HTTPException(
            status_code=400,
            detail="Candidate has no email address — cannot send notification"
        )

    job = db.query(Job).filter(Job.id == candidate.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    from app.services.email_service import send_shortlist_email
    success = await send_shortlist_email(
        candidate_name  = candidate.full_name or "Candidate",
        candidate_email = candidate.email,
        job_title       = job.title,
        hr_name         = body.hr_name,
        calendly_link   = body.calendly_link,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to send email")

    return {
        "message":    f"Interview invitation sent to {candidate.email}",
        "candidate":  candidate.full_name,
        "job":        job.title,
        "email_sent": True
    }


@router.post("/reject/{candidate_id}")
async def notify_reject(
    candidate_id: str,
    body: NotifyRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key),
):
    """Send rejection email to a candidate."""
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if not candidate.email:
        raise HTTPException(
            status_code=400,
            detail="Candidate has no email address — cannot send notification"
        )

    job = db.query(Job).filter(Job.id == candidate.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    from app.services.email_service import send_rejection_email
    success = await send_rejection_email(
        candidate_name  = candidate.full_name or "Candidate",
        candidate_email = candidate.email,
        job_title       = job.title,
        hr_name         = body.hr_name,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to send email")

    return {
        "message":    f"Rejection email sent to {candidate.email}",
        "candidate":  candidate.full_name,
        "job":        job.title,
        "email_sent": True
    }
