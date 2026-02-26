import json
import asyncio
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.job import Job
from app.models.candidate import Candidate
from app.models.screening import Screening

GEMINI_DELAY = 4.5  # seconds between Gemini calls — stays under 15 req/min free tier limit

async def run_screening_pipeline(job_id: str, screening_id: str):
    db = SessionLocal()
    try:
        screening = db.query(Screening).filter(Screening.id == screening_id).first()
        screening.status = "processing"
        db.commit()

        job = db.query(Job).filter(Job.id == job_id).first()
        candidates = db.query(Candidate).filter(Candidate.job_id == job_id).all()

        print(f"🚀 Starting screening for: {job.title} | {len(candidates)} candidates")

        scored    = await stage_score_candidates(job, candidates)
        verified  = await stage_verify_profiles(scored)
        ranked    = await stage_rank_and_finalise(verified)
        await stage_save_results(job_id, ranked, db)

        screening.status = "completed"
        screening.completed_at = datetime.utcnow()
        db.query(Job).filter(Job.id == job_id).update({"status": "completed"})
        db.commit()
        print(f"✅ Screening complete for: {job.title}")

    except Exception as e:
        print(f"❌ Screening failed: {e}")
        import traceback; traceback.print_exc()
        try:
            screening = db.query(Screening).filter(Screening.id == screening_id).first()
            if screening:
                screening.status = "failed"
                screening.error_message = str(e)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


async def stage_score_candidates(job, candidates) -> List[dict]:
    """Score each CV against the JD using Gemini — with rate limit delay between calls."""
    from app.services.llm_service import get_scoring_response

    scored = []
    total = len(candidates)

    for i, candidate in enumerate(candidates):
        print(f"  Scoring {i+1}/{total}: {candidate.full_name}")

        # Rate limit guard — wait between calls to stay under Gemini free tier limit
        if i > 0:
            await asyncio.sleep(GEMINI_DELAY)

        try:
            prompt = f"""You are a recruitment screening assistant. Score this candidate for the job below.
Return ONLY a valid JSON object, no markdown, no backticks.

JOB TITLE: {job.title}
JOB DESCRIPTION: {(job.description or '')[:1500]}
REQUIRED SKILLS: {job.required_skills}
MINIMUM EXPERIENCE: {job.min_experience_years} years

CANDIDATE:
Name: {candidate.full_name or 'Unknown'}
Skills: {candidate.skills or 'Not specified'}
Experience: {candidate.experience_years or 0} years
Education: {candidate.education or 'Not specified'}
Work History: {candidate.work_history or 'Not specified'}

Score 0-100 based on: skills match (35%), experience (20%), skills coverage (20%), education (10%), fit (15%).

Return ONLY this JSON:
{{
    "match_score": 75,
    "justification": "2-3 sentence explanation of the score",
    "red_flags": "any concerns or null",
    "skills_matched": "skills the candidate has from required list",
    "skills_missing": "required skills the candidate lacks"
}}"""

            # 20 second timeout per Gemini call — if it hangs, move on
            response = await asyncio.wait_for(
                get_scoring_response(prompt),
                timeout=20.0
            )
            clean = response.strip()
            if "```json" in clean:
                clean = clean.split("```json")[1].split("```")[0].strip()
            elif "```" in clean:
                clean = clean.split("```")[1].split("```")[0].strip()

            result = json.loads(clean)
            score = max(0, min(100, int(result.get("match_score", 0))))

            scored.append({
                "candidate_id": candidate.id,
                "full_name": candidate.full_name,
                "email": candidate.email,
                "skills": candidate.skills,
                "experience_years": candidate.experience_years,
                "match_score": score,
                "justification": result.get("justification", ""),
                "red_flags": result.get("red_flags"),
                "skills_matched": result.get("skills_matched", ""),
                "skills_missing": result.get("skills_missing", ""),
                "linkedin_url": candidate.linkedin_url,
                "github_url": candidate.github_url,
            })
            print(f"  ✓ {candidate.full_name}: {score}%")

        except asyncio.TimeoutError:
            print(f"  ⚠ Timeout scoring {candidate.full_name} — assigning 0")
            scored.append(_fallback(candidate, "Gemini timed out"))

        except (json.JSONDecodeError, Exception) as e:
            print(f"  ✗ Failed scoring {candidate.full_name}: {e}")
            scored.append(_fallback(candidate, str(e)))

    return scored


def _fallback(candidate, reason: str) -> dict:
    return {
        "candidate_id": candidate.id,
        "full_name": candidate.full_name,
        "email": candidate.email,
        "skills": candidate.skills,
        "experience_years": candidate.experience_years,
        "match_score": 0,
        "justification": f"Could not score this candidate automatically. Reason: {reason}",
        "red_flags": "Automatic scoring failed — review manually.",
        "linkedin_url": candidate.linkedin_url,
        "github_url": candidate.github_url,
    }


async def stage_verify_profiles(scored_candidates: List[dict]) -> List[dict]:
    """Verify LinkedIn and GitHub profiles — skips gracefully if unconfigured or slow."""
    from app.services.linkedin_service import verify_linkedin
    from app.services.github_service import verify_github

    for candidate in scored_candidates:
        bonus = 0

        # LinkedIn — 8 second timeout
        if candidate.get("linkedin_url"):
            try:
                data = await asyncio.wait_for(
                    verify_linkedin(candidate["linkedin_url"]),
                    timeout=8.0
                )
                if data:
                    candidate["linkedin_verified"] = data
                    bonus += 5
                    candidate["justification"] += " LinkedIn profile verified."
            except (asyncio.TimeoutError, Exception) as e:
                print(f"  LinkedIn skip ({candidate['full_name']}): {e}")

        # GitHub — 8 second timeout
        if candidate.get("github_url"):
            try:
                data = await asyncio.wait_for(
                    verify_github(candidate["github_url"]),
                    timeout=8.0
                )
                if data and data.get("public_repos", 0) > 5:
                    candidate["github_verified"] = data
                    bonus += 5
                    candidate["justification"] += f" Active GitHub: {data.get('public_repos')} repos."
            except (asyncio.TimeoutError, Exception) as e:
                print(f"  GitHub skip ({candidate['full_name']}): {e}")

        candidate["match_score"] = min(100, candidate["match_score"] + bonus)

    return scored_candidates


async def stage_rank_and_finalise(scored_candidates: List[dict]) -> List[dict]:
    ranked = sorted(scored_candidates, key=lambda x: x["match_score"], reverse=True)
    for i, c in enumerate(ranked):
        c["rank"] = i + 1
    return ranked


async def stage_save_results(job_id: str, ranked: List[dict], db: Session):
    for c in ranked:
        db.query(Candidate).filter(Candidate.id == c["candidate_id"]).update({
            "match_score":        c["match_score"],
            "rank":               c["rank"],
            "score_justification": c.get("justification"),
            "red_flags":          c.get("red_flags"),
        })
    db.commit()
    print(f"  💾 Saved {len(ranked)} candidate results")
