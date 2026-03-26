"""
Lektes Analytics Endpoint
GET /api/v1/analytics/summary  — overall platform stats
GET /api/v1/analytics/screening/{job_id} — per-job analytics
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from app.core.database import get_db
from app.core.security import require_api_key
from app.models.job import Job
from app.models.candidate import Candidate
from app.models.feedback import Feedback
from typing import Optional
import datetime

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary")
async def get_summary(
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key)
):
    """
    Overall platform analytics — answers Google's question about
    'what analytics have you done on the results'.
    """
    # Core counts
    total_jobs       = db.query(func.count(Job.id)).scalar() or 0
    total_candidates = db.query(func.count(Candidate.id)).scalar() or 0
    total_screened   = db.query(func.count(Candidate.id)).filter(
                           Candidate.match_score != None).scalar() or 0

    # Score distribution
    strong  = db.query(func.count(Candidate.id)).filter(Candidate.match_score >= 70).scalar() or 0
    partial = db.query(func.count(Candidate.id)).filter(
                  Candidate.match_score >= 45, Candidate.match_score < 70).scalar() or 0
    weak    = db.query(func.count(Candidate.id)).filter(
                  Candidate.match_score < 45,  Candidate.match_score != None).scalar() or 0

    # Average score
    avg_score = db.query(func.avg(Candidate.match_score)).filter(
                    Candidate.match_score != None).scalar()
    avg_score = round(float(avg_score), 1) if avg_score else 0

    # Feedback stats
    total_feedback  = db.query(func.count(Feedback.id)).scalar() or 0
    shortlisted     = db.query(func.count(Feedback.id)).filter(
                          Feedback.decision == 'shortlist').scalar() or 0
    rejected        = db.query(func.count(Feedback.id)).filter(
                          Feedback.decision == 'reject').scalar() or 0

    shortlist_rate = round((shortlisted / total_feedback * 100), 1) if total_feedback > 0 else 0

    # CVs per job average
    avg_cvs_per_job = round(total_candidates / total_jobs, 1) if total_jobs > 0 else 0

    # Top scoring candidates (last 10)
    top_candidates = db.query(Candidate).filter(
        Candidate.match_score != None
    ).order_by(Candidate.match_score.desc()).limit(10).all()

    return {
        "overview": {
            "total_jobs_created":     total_jobs,
            "total_cvs_uploaded":     total_candidates,
            "total_cvs_screened":     total_screened,
            "avg_cvs_per_job":        avg_cvs_per_job,
            "average_match_score":    avg_score,
        },
        "score_distribution": {
            "strong_match_pct":   round(strong  / total_screened * 100, 1) if total_screened else 0,
            "partial_match_pct":  round(partial / total_screened * 100, 1) if total_screened else 0,
            "weak_match_pct":     round(weak    / total_screened * 100, 1) if total_screened else 0,
            "strong_count":  strong,
            "partial_count": partial,
            "weak_count":    weak,
        },
        "hr_feedback": {
            "total_decisions_made": total_feedback,
            "shortlisted":          shortlisted,
            "rejected":             rejected,
            "shortlist_rate_pct":   shortlist_rate,
        },
        "top_candidates": [
            {
                "name":        c.full_name,
                "score":       c.match_score,
                "experience":  c.experience_years,
                "education":   c.education,
            }
            for c in top_candidates
        ],
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z"
    }


@router.get("/screening/{job_id}")
async def get_screening_analytics(
    job_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key)
):
    """
    Per-job screening analytics — score breakdown for a specific screening session.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Job not found")

    candidates = db.query(Candidate).filter(
        Candidate.job_id == job_id,
        Candidate.match_score != None
    ).order_by(Candidate.match_score.desc()).all()

    if not candidates:
        return {"job_id": job_id, "message": "No screened candidates found"}

    scores    = [c.match_score for c in candidates]
    avg       = round(sum(scores) / len(scores), 1)
    highest   = max(scores)
    lowest    = min(scores)
    spread    = round(highest - lowest, 1)

    strong  = sum(1 for s in scores if s >= 70)
    partial = sum(1 for s in scores if 45 <= s < 70)
    weak    = sum(1 for s in scores if s < 45)

    # Feedback for this job
    feedbacks = db.query(Feedback).filter(
        Feedback.candidate_id.in_([c.id for c in candidates])
    ).all()
    fb_map = {f.candidate_id: f.decision for f in feedbacks}

    return {
        "job_id":    job_id,
        "job_title": job.title,
        "summary": {
            "total_candidates":  len(candidates),
            "average_score":     avg,
            "highest_score":     highest,
            "lowest_score":      lowest,
            "score_spread":      spread,
        },
        "distribution": {
            "strong_match":  strong,
            "partial_match": partial,
            "weak_match":    weak,
        },
        "candidates": [
            {
                "rank":       i + 1,
                "name":       c.full_name,
                "score":      c.match_score,
                "experience": c.experience_years,
                "hr_decision": fb_map.get(c.id, "pending"),
            }
            for i, c in enumerate(candidates)
        ],
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z"
    }
