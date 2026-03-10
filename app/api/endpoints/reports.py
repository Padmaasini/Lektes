from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.job import Job
from app.models.candidate import Candidate
from app.models.screening import Screening
import re as _re

router = APIRouter()


def _display_name(candidate) -> str:
    """
    Return a human-readable display name for a candidate.
    Falls back to email-derived name if full_name is null or UUID-like.
    """
    name = candidate.full_name
    # Reject UUID-like strings (hex chars and spaces/dashes)
    if name:
        if _re.match(r'^[0-9a-fA-F]{4,}[\s\-]', name.strip()):
            name = None
        elif _re.search(r'\d{4,}', name):
            name = None
    if not name and candidate.email:
        local = candidate.email.split('@')[0]
        parts = _re.split(r'[._\-]', local)
        parts = [p for p in parts if not p.isdigit() and len(p) > 1]
        if parts:
            name = ' '.join(p.capitalize() for p in parts)
    return name or 'Unknown'


def _candidate_list(job_id: str, db: Session, limit: int = None):
    q = (
        db.query(Candidate)
        .filter(Candidate.job_id == job_id, Candidate.match_score != None)
        .order_by(Candidate.match_score.desc())
    )
    if limit:
        q = q.limit(limit)
    return q.all()


@router.get("/{job_id}")
async def get_report(job_id: str, db: Session = Depends(get_db)):
    """Return the ranked screening report as JSON for the frontend."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    candidates = _candidate_list(job_id, db)
    if not candidates:
        raise HTTPException(status_code=404, detail="No screened candidates found. Run screening first.")

    return {
        "job_title":                  job.title,
        "job_id":                     job_id,
        "hr_email":                   job.hr_email,
        "min_experience_years":       job.min_experience_years or 0,
        "max_experience_years":       job.max_experience_years or 0,
        "total_candidates":           db.query(Candidate).filter(Candidate.job_id == job_id).count(),
        "total_candidates_screened":  db.query(Candidate).filter(Candidate.job_id == job_id).count(),
        "top_candidates": [
            {
                "rank":             idx + 1,
                "candidate_id":     c.id,
                "name":             _display_name(c),
                "email":            c.email,
                "match_score":      round(c.match_score, 1),
                "match_percentage": f"{round(c.match_score, 1)}%",
                "skills":           c.skills,
                "experience_years": c.experience_years,
                "education":        c.education,
                "justification":    c.score_justification,
                "red_flags":        c.red_flags,
                "linkedin_url":     c.linkedin_url,
                "github_url":       c.github_url,
            }
            for idx, c in enumerate(candidates)
        ],
    }


@router.post("/{job_id}/send")
async def send_report(job_id: str, db: Session = Depends(get_db)):
    """
    Generate PDF report + interview questions and email to HR.
    PDF is attached. Questions with likely answers are in the email body.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    candidates = _candidate_list(job_id, db, limit=5)  # top 5 for questions
    if not candidates:
        raise HTTPException(status_code=404, detail="No screened candidates found.")

    # ── Step 1: Generate PDF ──────────────────────────────────────────────
    try:
        from app.services.pdf_generator import generate_pdf_report
    except ImportError:
        try:
            from app.services.report_generator import generate_pdf_report
        except ImportError:
            raise HTTPException(status_code=500, detail="PDF generator not found.")

    candidate_dicts = [
        {
            "rank":             idx + 1,
            "name":             _display_name(c),
            "email":            c.email,
            "match_score":      round(c.match_score or 0, 1),
            "skills":           c.skills,
            "experience_years": c.experience_years,
            "education":        c.education,
            "justification":    c.score_justification,
            "red_flags":        c.red_flags,
            "linkedin_url":     c.linkedin_url,
            "github_url":       c.github_url,
        }
        for idx, c in enumerate(_candidate_list(job_id, db, limit=10))
    ]

    pdf_bytes = generate_pdf_report(
        job_title=job.title,
        hr_email=job.hr_email,
        candidates=candidate_dicts
    )

    # ── Step 2: Generate interview questions for top candidates ───────────
    from app.services.question_generator import generate_interview_questions
    questions_by_candidate = {}

    for idx, c in enumerate(candidates):
        try:
            qs = await generate_interview_questions(job, c)
            questions_by_candidate[c.id] = {
                "candidate_name": _display_name(c),
                "match_score":    round(c.match_score or 0, 1),
                "rank":           idx + 1,
                "questions":      qs,
            }
            print(f"  ✓ Questions generated for {_display_name(c)}")
        except Exception as e:
            print(f"  ✗ Questions failed for {_display_name(c)}: {e}")

    # ── Step 3: Send email with PDF attachment + questions ────────────────
    from app.services.email_service import send_report_email
    all_candidates = _candidate_list(job_id, db, limit=10)

    success = await send_report_email(
        job=job,
        candidates=all_candidates,
        pdf_bytes=pdf_bytes,
        questions_by_candidate=questions_by_candidate
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to send email. Check RESEND_API_KEY.")

    # Mark report sent
    screening = db.query(Screening).filter(Screening.job_id == job_id).first()
    if screening:
        screening.report_sent = "true"
        db.commit()

    return {"message": f"Report + interview questions emailed to {job.hr_email}"}


@router.post("/{job_id}/questions/{candidate_id}")
async def generate_screening_questions(
    job_id: str,
    candidate_id: str,
    db: Session = Depends(get_db)
):
    """Generate interview questions for a specific candidate on demand."""
    job       = db.query(Job).filter(Job.id == job_id).first()
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()

    if not job or not candidate:
        raise HTTPException(status_code=404, detail="Job or candidate not found")

    from app.services.question_generator import generate_interview_questions
    questions = await generate_interview_questions(job, candidate)

    return {
        "candidate_id":   candidate_id,
        "candidate_name": _display_name(candidate),
        "job_title":      job.title,
        "match_score":    round(candidate.match_score or 0, 1),
        "questions":      questions,
    }
