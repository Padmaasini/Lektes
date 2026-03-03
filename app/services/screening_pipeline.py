import json
import asyncio
from typing import List
from datetime import datetime
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.job import Job
from app.models.candidate import Candidate
from app.models.screening import Screening

GROQ_DELAY = 3.0  # seconds between Groq calls — stays well under free tier limits

async def run_screening_pipeline(job_id: str, screening_id: str):
    db = SessionLocal()
    try:
        screening = db.query(Screening).filter(Screening.id == screening_id).first()
        screening.status = "processing"
        db.commit()

        job        = db.query(Job).filter(Job.id == job_id).first()
        candidates = db.query(Candidate).filter(Candidate.job_id == job_id).all()
        print(f"🚀 Screening: {job.title} | {len(candidates)} candidates")

        scored   = await stage_extract_and_score(job, candidates)
        verified = await stage_verify_profiles(scored)
        ranked   = sorted(verified, key=lambda x: x["match_score"], reverse=True)
        for i, c in enumerate(ranked):
            c["rank"] = i + 1

        await stage_save_results(job_id, ranked, db)

        screening.status       = "completed"
        screening.completed_at = datetime.utcnow()
        db.query(Job).filter(Job.id == job_id).update({"status": "completed"})
        db.commit()
        print(f"✅ Screening complete: {job.title}")

    except Exception as e:
        print(f"❌ Screening failed: {e}")
        import traceback; traceback.print_exc()
        try:
            s = db.query(Screening).filter(Screening.id == screening_id).first()
            if s:
                s.status = "failed"
                s.error_message = str(e)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


async def stage_extract_and_score(job, candidates) -> List[dict]:
    """
    Combined extraction + scoring in ONE Groq call per candidate.
    Uses raw_text from the DB — no file reading needed.
    Adds delay between calls to respect free tier rate limits.
    """
    from app.services.llm_service import get_scoring_response
    scored = []
    total  = len(candidates)

    for i, candidate in enumerate(candidates):
        print(f"  Processing {i+1}/{total}: {candidate.full_name or candidate.email or 'Unknown'}")

        if i > 0:
            await asyncio.sleep(GROQ_DELAY)

        raw_text = candidate.cv_raw_text or ""
        if not raw_text:
            print(f"  ⚠ No raw text for candidate {candidate.id} — skipping")
            scored.append(_fallback(candidate, "No CV text found"))
            continue

        try:
            prompt = f"""You are a recruitment screening assistant. You have two tasks:

TASK 1 - Extract structured information from this CV.
TASK 2 - Score this candidate for the job below.

JOB TITLE: {job.title}
JOB DESCRIPTION: {(job.description or '')[:1000]}
REQUIRED SKILLS: {job.required_skills}
MINIMUM EXPERIENCE: {job.min_experience_years} years

CV RAW TEXT:
{raw_text[:3000]}

Return ONLY this JSON object, nothing else:
{{
    "full_name": "candidate full name from CV",
    "email": "email address or null",
    "phone": "phone number or null",
    "location": "city and country or null",
    "skills": "comma separated list of ALL technical skills mentioned",
    "experience_years": 4,
    "education": "degree, field, university name and year",
    "work_history": "2-3 sentence summary of their work history",
    "match_score": 75,
    "justification": "2-3 sentences explaining the score based on the job requirements",
    "red_flags": "any concerns about the candidate or null",
    "skills_matched": "required skills this candidate has",
    "skills_missing": "required skills this candidate lacks"
}}

Rules:
- experience_years must be an integer
- skills must be a comma-separated string
- match_score must be 0-100 based on: skills match 35%, experience 20%, skills coverage 20%, education 10%, fit 15%
- Return ONLY the JSON, no explanation, no markdown"""

            response = await asyncio.wait_for(
                get_scoring_response(prompt),
                timeout=25.0
            )

            clean = response.strip()
            if "```json" in clean:
                clean = clean.split("```json")[1].split("```")[0].strip()
            elif "```" in clean:
                clean = clean.split("```")[1].split("```")[0].strip()

            result = json.loads(clean)

            # Update candidate fields in DB immediately
            score = max(0, min(100, int(result.get("match_score", 0))))

            scored.append({
                "candidate_id":    candidate.id,
                "full_name":       result.get("full_name") or candidate.full_name,
                "email":           result.get("email") or candidate.email,
                "skills":          result.get("skills", ""),
                "experience_years": int(result.get("experience_years") or 0),
                "education":       result.get("education"),
                "work_history":    result.get("work_history"),
                "match_score":     score,
                "justification":   result.get("justification", ""),
                "red_flags":       result.get("red_flags"),
                "linkedin_url":    candidate.linkedin_url,
                "github_url":      candidate.github_url,
            })
            print(f"  ✓ {result.get('full_name') or candidate.full_name}: {score}%")

        except asyncio.TimeoutError:
            print(f"  ⚠ Timeout on candidate {i+1}")
            scored.append(_fallback(candidate, "Request timed out"))
        except (json.JSONDecodeError, Exception) as e:
            print(f"  ✗ Error on candidate {i+1}: {e}")
            scored.append(_fallback(candidate, str(e)))

    return scored


def _fallback(candidate, reason: str) -> dict:
    return {
        "candidate_id":    candidate.id,
        "full_name":       candidate.full_name,
        "email":           candidate.email,
        "skills":          candidate.skills or "",
        "experience_years": candidate.experience_years or 0,
        "education":       candidate.education,
        "work_history":    candidate.work_history,
        "match_score":     0,
        "justification":   f"Could not score automatically. Reason: {reason}",
        "red_flags":       "Automatic scoring failed — review manually.",
        "linkedin_url":    candidate.linkedin_url,
        "github_url":      candidate.github_url,
    }


async def stage_verify_profiles(scored: List[dict]) -> List[dict]:
    """Verify LinkedIn and GitHub — skips gracefully if unconfigured."""
    from app.services.linkedin_service import verify_linkedin
    from app.services.github_service import verify_github

    for c in scored:
        bonus = 0
        if c.get("linkedin_url"):
            try:
                data = await asyncio.wait_for(verify_linkedin(c["linkedin_url"]), timeout=8.0)
                if data:
                    bonus += 5
                    c["justification"] += " LinkedIn profile verified."
            except Exception:
                pass
        if c.get("github_url"):
            try:
                data = await asyncio.wait_for(verify_github(c["github_url"]), timeout=8.0)
                if data and data.get("public_repos", 0) > 5:
                    bonus += 5
                    c["justification"] += f" Active GitHub: {data.get('public_repos')} repos."
            except Exception:
                pass
        c["match_score"] = min(100, c["match_score"] + bonus)

    return scored


async def stage_save_results(job_id: str, ranked: List[dict], db: Session):
    """Save all extracted fields + scores back to DB."""
    for c in ranked:
        db.query(Candidate).filter(Candidate.id == c["candidate_id"]).update({
            "full_name":        c.get("full_name"),
            "email":            c.get("email"),
            "skills":           c.get("skills"),
            "experience_years": c.get("experience_years", 0),
            "education":        c.get("education"),
            "work_history":     c.get("work_history"),
            "match_score":      c["match_score"],
            "rank":             c["rank"],
            "score_justification": c.get("justification"),
            "red_flags":        c.get("red_flags"),
        })
    db.commit()
    print(f"  💾 Saved {len(ranked)} results")
