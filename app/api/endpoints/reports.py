from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.job import Job
from app.models.candidate import Candidate
from app.models.screening import Screening
from app.services.report_generator import generate_report

router = APIRouter()


@router.get("/{job_id}")
async def get_report(job_id: str, db: Session = Depends(get_db)):
    """
    Get the full ranked screening report for a job.
    Returns all scored candidates ordered by rank.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    candidates = (
        db.query(Candidate)
        .filter(Candidate.job_id == job_id)
        .filter(Candidate.match_score.isnot(None))
        .order_by(Candidate.rank)
        .all()
    )

    if not candidates:
        raise HTTPException(
            status_code=404,
            detail="No screened candidates found. Run screening first."
        )

    total = db.query(Candidate).filter(Candidate.job_id == job_id).count()

    return {
        "job_title":                  job.title,
        "job_id":                     job_id,
        "hr_email":                   job.hr_email,
        "total_candidates":           total,
        "total_candidates_screened":  len(candidates),
        "top_candidates": [
            {
                "rank":             c.rank or (idx + 1),
                "name":             c.full_name or "Unknown",
                "email":            c.email or "—",
                "match_score":      round(c.match_score, 1),
                "match_percentage": f"{round(c.match_score, 1)}%",
                "skills":           c.skills or "—",
                "experience_years": c.experience_years or 0,
                "education":        c.education or "—",
                "work_history":     c.work_history or "—",
                "justification":    c.score_justification or "—",
                "red_flags":        c.red_flags or None,
                "linkedin_url":     c.linkedin_url or None,
                "github_url":       c.github_url or None,
            }
            for idx, c in enumerate(candidates)
        ]
    }


@router.post("/{job_id}/send", status_code=200)
async def send_report(job_id: str, db: Session = Depends(get_db)):
    """
    Send the screening report as a formatted HTML email to the HR contact.
    Requires GMAIL_USER and GMAIL_APP_PASSWORD set in Render environment.
    """
    from app.services.email_service import send_report_email

    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.hr_email:
        raise HTTPException(status_code=400, detail="No HR email set for this job")

    candidates = (
        db.query(Candidate)
        .filter(Candidate.job_id == job_id)
        .filter(Candidate.match_score.isnot(None))
        .order_by(Candidate.rank)
        .all()
    )

    if not candidates:
        raise HTTPException(
            status_code=400,
            detail="No scored candidates found — run screening first."
        )

    # Build candidate list for email
    candidate_list = [
        {
            "rank":             c.rank or (idx + 1),
            "name":             c.full_name or "Unknown",
            "email":            c.email or "—",
            "match_score":      round(c.match_score, 1),
            "experience_years": c.experience_years or 0,
            "justification":    c.score_justification or "—",
            "red_flags":        c.red_flags or None,
            "linkedin_url":     c.linkedin_url or None,
            "github_url":       c.github_url or None,
        }
        for idx, c in enumerate(candidates)
    ]

    try:
        await send_report_email(job.hr_email, job.title, candidate_list)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Email failed: {str(e)}. Check GMAIL_USER and GMAIL_APP_PASSWORD on Render."
        )

    # Mark report as sent
    screening = db.query(Screening).filter(Screening.job_id == job_id).first()
    if screening:
        screening.report_sent = "true"
        db.commit()

    return {
        "message":             f"Report sent to {job.hr_email}",
        "candidates_included": len(candidates)
    }


@router.post("/{job_id}/questions/{candidate_id}")
async def generate_screening_questions(
    job_id: str,
    candidate_id: str,
    db: Session = Depends(get_db)
):
    """
    Generate tailored technical interview questions for a specific candidate.
    """
    job       = db.query(Job).filter(Job.id == job_id).first()
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()

    if not job or not candidate:
        raise HTTPException(status_code=404, detail="Job or candidate not found")

    from app.services.question_generator import generate_technical_questions
    questions = await generate_technical_questions(job, candidate)

    return {
        "candidate_name": candidate.full_name,
        "job_title":      job.title,
        "questions":      questions
    }


@router.get("/debug/email-config")
async def debug_email_config():
    """
    Debug endpoint — check if Gmail credentials are loaded.
    Visit: /api/v1/reports/debug/email-config
    """
    from app.core.config import settings
    return {
        "GMAIL_USER_set":         bool(settings.GMAIL_USER),
        "GMAIL_USER_value":       settings.GMAIL_USER or "NOT SET",
        "GMAIL_APP_PASSWORD_set": bool(settings.GMAIL_APP_PASSWORD),
        "GMAIL_APP_PASSWORD_len": len(settings.GMAIL_APP_PASSWORD) if settings.GMAIL_APP_PASSWORD else 0,
        "GROQ_API_KEY_set":       bool(settings.GROQ_API_KEY),
    }


@router.get("/debug/smtp-test")
async def debug_smtp_test():
    """
    Test SMTP connection and login with exact error reporting.
    Visit: /api/v1/reports/debug/smtp-test
    Shows the exact Gmail error so we can diagnose the issue.
    """
    import smtplib
    from app.core.config import settings

    if not settings.GMAIL_USER or not settings.GMAIL_APP_PASSWORD:
        return {"status": "error", "message": "Credentials not set"}

    results = {}

    # Test port 465 SSL
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(settings.GMAIL_USER, settings.GMAIL_APP_PASSWORD)
        results["port_465_ssl"] = "✅ SUCCESS — login worked"
    except smtplib.SMTPAuthenticationError as e:
        results["port_465_ssl"] = f"❌ AUTH ERROR: {str(e)}"
    except Exception as e:
        results["port_465_ssl"] = f"❌ CONNECTION ERROR: {type(e).__name__}: {str(e)}"

    # Test port 587 TLS
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.GMAIL_USER, settings.GMAIL_APP_PASSWORD)
        results["port_587_tls"] = "✅ SUCCESS — login worked"
    except smtplib.SMTPAuthenticationError as e:
        results["port_587_tls"] = f"❌ AUTH ERROR: {str(e)}"
    except Exception as e:
        results["port_587_tls"] = f"❌ CONNECTION ERROR: {type(e).__name__}: {str(e)}"

    return {
        "gmail_user": settings.GMAIL_USER,
        "password_length": len(settings.GMAIL_APP_PASSWORD),
        "results": results,
        "next_steps": {
            "if_auth_error": "App Password is wrong — regenerate at myaccount.google.com → Security → App Passwords",
            "if_connection_error": "Render is blocking the port — use whichever port shows SUCCESS above",
        }
    }
