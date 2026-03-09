"""
Feedback endpoints — HR thumbs up/down on screened candidates.

POST /api/v1/feedback/{candidate_id}   — submit or update feedback
GET  /api/v1/feedback/job/{job_id}     — get all feedback for a job
GET  /api/v1/feedback/summary/{job_id} — aggregated stats for analytics
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from app.core.database import get_db
from app.core.security import require_api_key
from app.models.candidate import Candidate
from app.models.feedback import Feedback
from app.models.job import Job

router = APIRouter()


# ── SCHEMAS ──────────────────────────────────────────────────

class FeedbackSubmit(BaseModel):
    decision:     str            # "shortlist" or "reject"
    outcome:      Optional[str] = None   # "hired" | "interviewed" | "declined"
    notes:        Optional[str] = None
    submitted_by: Optional[str] = None  # HR email


class FeedbackResponse(BaseModel):
    id:           str
    candidate_id: str
    job_id:       str
    decision:     str
    outcome:      Optional[str]
    notes:        Optional[str]
    submitted_by: Optional[str]
    created_at:   datetime

    class Config:
        from_attributes = True


class FeedbackSummary(BaseModel):
    job_id:       str
    total:        int
    shortlisted:  int
    rejected:     int
    hired:        int
    interviewed:  int
    declined:     int


# ── ENDPOINTS ────────────────────────────────────────────────

@router.post("/{candidate_id}", response_model=FeedbackResponse, status_code=201)
async def submit_feedback(
    candidate_id: str,
    body: FeedbackSubmit,
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key),
):
    """
    Submit or update HR feedback for a candidate.
    If feedback already exists for this candidate, it is updated (upsert).

    decision: "shortlist" (thumbs up 👍) or "reject" (thumbs down 👎)
    outcome:  optional — fill in after interview: "hired" | "interviewed" | "declined"
    """
    # Validate decision value
    if body.decision not in ("shortlist", "reject"):
        raise HTTPException(
            status_code=400,
            detail="decision must be 'shortlist' or 'reject'"
        )

    # Validate outcome value if provided
    valid_outcomes = {"hired", "interviewed", "declined", None}
    if body.outcome not in valid_outcomes:
        raise HTTPException(
            status_code=400,
            detail="outcome must be 'hired', 'interviewed', 'declined', or null"
        )

    # Check candidate exists
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Upsert — update if feedback already exists for this candidate
    existing = db.query(Feedback).filter(Feedback.candidate_id == candidate_id).first()
    if existing:
        existing.decision     = body.decision
        existing.outcome      = body.outcome
        existing.notes        = body.notes
        existing.submitted_by = body.submitted_by
        existing.updated_at   = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing

    # Create new feedback record
    feedback = Feedback(
        candidate_id = candidate_id,
        job_id       = candidate.job_id,
        decision     = body.decision,
        outcome      = body.outcome,
        notes        = body.notes,
        submitted_by = body.submitted_by,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


@router.get("/job/{job_id}", response_model=List[FeedbackResponse])
async def get_job_feedback(
    job_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key),
):
    """Get all feedback records for a job — used to show saved HR decisions."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return db.query(Feedback).filter(Feedback.job_id == job_id).all()


@router.get("/summary/{job_id}", response_model=FeedbackSummary)
async def get_feedback_summary(
    job_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key),
):
    """Aggregated feedback stats for a job — for analytics dashboard."""
    records = db.query(Feedback).filter(Feedback.job_id == job_id).all()

    return FeedbackSummary(
        job_id      = job_id,
        total       = len(records),
        shortlisted = sum(1 for r in records if r.decision == "shortlist"),
        rejected    = sum(1 for r in records if r.decision == "reject"),
        hired       = sum(1 for r in records if r.outcome  == "hired"),
        interviewed = sum(1 for r in records if r.outcome  == "interviewed"),
        declined    = sum(1 for r in records if r.outcome  == "declined"),
    )


@router.patch("/{candidate_id}/outcome")
async def update_outcome(
    candidate_id: str,
    outcome: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key),
):
    """
    Update the post-interview outcome for a candidate.
    Called after the HR team completes interviews.
    outcome: "hired" | "interviewed" | "declined"
    """
    valid_outcomes = {"hired", "interviewed", "declined"}
    if outcome not in valid_outcomes:
        raise HTTPException(
            status_code=400,
            detail=f"outcome must be one of: {', '.join(valid_outcomes)}"
        )

    feedback = db.query(Feedback).filter(Feedback.candidate_id == candidate_id).first()
    if not feedback:
        raise HTTPException(
            status_code=404,
            detail="No feedback found for this candidate — submit feedback first"
        )

    feedback.outcome    = outcome
    feedback.updated_at = datetime.utcnow()
    db.commit()

    return {"message": f"Outcome updated to '{outcome}'", "candidate_id": candidate_id}
