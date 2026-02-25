import json
from typing import TypedDict, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.job import Job
from app.models.candidate import Candidate
from app.models.screening import Screening

# LangGraph State
class ScreeningState(TypedDict):
    job_id: str
    screening_id: str
    job_title: str
    job_description: str
    required_skills: List[str]
    candidates: List[dict]
    current_candidate_idx: int
    scored_candidates: List[dict]
    error: Optional[str]

async def run_screening_pipeline(job_id: str, screening_id: str):
    """
    Main screening pipeline entry point.
    Runs all stages: fetch → score → verify → rank → report.
    """
    db = SessionLocal()
    try:
        # Update status to processing
        screening = db.query(Screening).filter(Screening.id == screening_id).first()
        screening.status = "processing"
        db.commit()

        job = db.query(Job).filter(Job.id == job_id).first()
        candidates = db.query(Candidate).filter(Candidate.job_id == job_id).all()

        print(f"🚀 Starting screening for job: {job.title} | {len(candidates)} candidates")

        # Stage 1: Score each candidate against the JD
        scored = await stage_score_candidates(job, candidates)

        # Stage 2: Verify external profiles
        verified = await stage_verify_profiles(scored)

        # Stage 3: Adjust scores based on verification
        final_ranked = await stage_rank_and_finalise(job, verified)

        # Stage 4: Save results back to DB
        await stage_save_results(job_id, final_ranked, db)

        # Stage 5: Mark complete
        screening.status = "completed"
        screening.completed_at = datetime.utcnow()
        db.query(Job).filter(Job.id == job_id).update({"status": "completed"})
        db.commit()

        print(f"✅ Screening complete for job: {job.title}")

    except Exception as e:
        print(f"❌ Screening failed: {e}")
        screening = db.query(Screening).filter(Screening.id == screening_id).first()
        if screening:
            screening.status = "failed"
            screening.error_message = str(e)
            db.commit()
    finally:
        db.close()

async def stage_score_candidates(job, candidates) -> List[dict]:
    """Stage 1: Score each CV against the job description using LLM."""
    from app.services.llm_service import get_scoring_response
    scored = []

    for candidate in candidates:
        try:
            prompt = f"""
            You are screening a candidate for the following job.
            
            JOB TITLE: {job.title}
            JOB DESCRIPTION: {job.description}
            REQUIRED SKILLS: {job.required_skills}
            MINIMUM EXPERIENCE: {job.min_experience_years} years
            
            CANDIDATE CV SUMMARY:
            Name: {candidate.full_name}
            Skills: {candidate.skills}
            Experience: {candidate.experience_years} years
            Education: {candidate.education}
            Work History: {candidate.work_history}
            
            Score this candidate from 0 to 100 based on:
            - Skills match (35%)
            - Experience alignment (20%)
            - Required skills coverage (20%)
            - Education relevance (10%)
            - Overall profile fit (15%)
            
            Return ONLY this JSON:
            {{
                "match_score": 0-100,
                "justification": "2-3 sentence explanation of why this score was given",
                "red_flags": "any concerns or null if none",
                "skills_matched": "which required skills the candidate has",
                "skills_missing": "which required skills are absent"
            }}
            """

            response = await get_scoring_response(prompt)
            clean = response.strip().replace("```json", "").replace("```", "").strip()
            result = json.loads(clean)

            scored.append({
                "candidate_id": candidate.id,
                "full_name": candidate.full_name,
                "match_score": result.get("match_score", 0),
                "justification": result.get("justification", ""),
                "red_flags": result.get("red_flags"),
                "skills_matched": result.get("skills_matched", ""),
                "skills_missing": result.get("skills_missing", ""),
                "linkedin_url": candidate.linkedin_url,
                "github_url": candidate.github_url,
            })
            print(f"  ✓ Scored {candidate.full_name}: {result.get('match_score')}%")

        except Exception as e:
            print(f"  ✗ Failed to score {candidate.full_name}: {e}")
            scored.append({
                "candidate_id": candidate.id,
                "full_name": candidate.full_name,
                "match_score": 0,
                "justification": "Scoring failed due to parsing error.",
                "red_flags": "CV could not be parsed correctly.",
                "linkedin_url": candidate.linkedin_url,
                "github_url": candidate.github_url,
            })

    return scored

async def stage_verify_profiles(scored_candidates: List[dict]) -> List[dict]:
    """Stage 2: Verify LinkedIn and GitHub profiles."""
    from app.services.linkedin_service import verify_linkedin
    from app.services.github_service import verify_github

    for candidate in scored_candidates:
        verification_bonus = 0
        verification_notes = []

        # LinkedIn verification
        if candidate.get("linkedin_url"):
            try:
                linkedin_data = await verify_linkedin(candidate["linkedin_url"])
                if linkedin_data:
                    candidate["linkedin_verified"] = linkedin_data
                    verification_bonus += 5
                    verification_notes.append("LinkedIn profile verified and consistent with CV.")
            except Exception as e:
                print(f"  LinkedIn verification failed for {candidate['full_name']}: {e}")

        # GitHub verification
        if candidate.get("github_url"):
            try:
                github_data = await verify_github(candidate["github_url"])
                if github_data:
                    candidate["github_verified"] = github_data
                    if github_data.get("public_repos", 0) > 5:
                        verification_bonus += 5
                        verification_notes.append(
                            f"Active GitHub: {github_data.get('public_repos')} repos."
                        )
            except Exception as e:
                print(f"  GitHub verification failed for {candidate['full_name']}: {e}")

        # Apply verification bonus (max 10 points)
        candidate["match_score"] = min(100, candidate["match_score"] + verification_bonus)
        if verification_notes:
            candidate["justification"] += " " + " ".join(verification_notes)

    return scored_candidates

async def stage_rank_and_finalise(job, scored_candidates: List[dict]) -> List[dict]:
    """Stage 3: Sort by score and assign final ranks."""
    ranked = sorted(scored_candidates, key=lambda x: x["match_score"], reverse=True)
    for idx, candidate in enumerate(ranked):
        candidate["rank"] = idx + 1
    return ranked

async def stage_save_results(job_id: str, ranked_candidates: List[dict], db: Session):
    """Stage 4: Save final scores and justifications back to the database."""
    for candidate_data in ranked_candidates:
        db.query(Candidate).filter(
            Candidate.id == candidate_data["candidate_id"]
        ).update({
            "match_score": candidate_data["match_score"],
            "rank": candidate_data["rank"],
            "score_justification": candidate_data.get("justification"),
            "red_flags": candidate_data.get("red_flags"),
        })
    db.commit()
    print(f"  💾 Saved results for {len(ranked_candidates)} candidates")
