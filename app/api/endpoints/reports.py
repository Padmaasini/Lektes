from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.job import Job
from app.models.candidate import Candidate
from app.models.screening import Screening
from app.services.report_generator import generate_report
from app.services.email_service import send_report_email

router = APIRouter()

@router.get("/{job_id}")
async def get_report(job_id: str, db: Session = Depends(get_db)):
    """
    Get the full ranked screening report for a job.
    Returns top 10 candidates with scores and justifications.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    candidates = db.query(Candidate)\
        .filter(Candidate.job_id == job_id)\
        .filter(Candidate.match_score != None)\
        .order_by(Candidate.match_score.desc())\
        .limit(10)\
        .all()

    if not candidates:
        raise HTTPException(
            status_code=404,
            detail="No screened candidates found. Run screening first."
        )

    report = {
        "job_title": job.title,
        "job_id": job_id,
        "total_candidates_screened": db.query(Candidate).filter(Candidate.job_id == job_id).count(),
        "top_candidates": [
            {
                "rank": idx + 1,
                "name": c.full_name,
                "email": c.email,
                "match_score": round(c.match_score, 1),
                "match_percentage": f"{round(c.match_score, 1)}%",
                "skills": c.skills,
                "experience_years": c.experience_years,
                "justification": c.score_justification,
                "red_flags": c.red_flags,
                "linkedin_url": c.linkedin_url,
                "github_url": c.github_url,
            }
            for idx, c in enumerate(candidates)
        ]
    }

    return report

@router.post("/{job_id}/send")
async def send_report(job_id: str, db: Session = Depends(get_db)):
    """
    Send the screening report to the HR email address on file.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    candidates = db.query(Candidate)\
        .filter(Candidate.job_id == job_id)\
        .filter(Candidate.match_score != None)\
        .order_by(Candidate.match_score.desc())\
        .limit(10)\
        .all()

    if not candidates:
        raise HTTPException(status_code=404, detail="No screened candidates found.")

    success = await send_report_email(job, candidates)

    if success:
        screening = db.query(Screening).filter(Screening.job_id == job_id).first()
        if screening:
            screening.report_sent = "true"
            db.commit()
        return {"message": f"Report sent successfully to {job.hr_email}"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send email. Check Gmail credentials.")

@router.post("/{job_id}/questions/{candidate_id}")
async def generate_screening_questions(
    job_id: str,
    candidate_id: str,
    db: Session = Depends(get_db)
):
    """
    Generate 2-3 technical screening questions for a specific candidate.
    Only call this if the HR requests it.
    Returns questions + answer blueprint.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()

    if not job or not candidate:
        raise HTTPException(status_code=404, detail="Job or candidate not found")

    from app.services.question_generator import generate_technical_questions
    questions = await generate_technical_questions(job, candidate)

    return {
        "candidate_name": candidate.full_name,
        "job_title": job.title,
        "questions": questions
    }
