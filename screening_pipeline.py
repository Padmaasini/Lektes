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

    min_exp = job.min_experience_years or 0
    max_exp = job.max_experience_years or 0  # 0 = no upper limit

    # Build experience requirement string for the prompt
    if max_exp > 0:
        exp_requirement = f"BETWEEN {min_exp} AND {max_exp} years"
        exp_rule = (
            f"The role requires {min_exp}–{max_exp} years of experience. "
            f"Candidates with fewer than {min_exp} years OR more than {max_exp} years "
            f"are a POOR experience fit and MUST receive a significantly lower score. "
            f"Being overqualified (too many years) is just as problematic as being underqualified. "
            f"Experience outside this range should reduce the score by 20–35 points unless "
            f"their skills are exceptional."
        )
    elif min_exp == 0:
        exp_requirement = "0 years (fresher / entry level welcome)"
        exp_rule = (
            "This is an entry-level or fresher role. Candidates with more than 2 years "
            "of experience are OVERQUALIFIED and should receive a lower score — they are "
            "unlikely to stay in the role and may expect more than this position offers. "
            "Reduce score by 15–25 points for candidates with 3+ years experience."
        )
    else:
        exp_requirement = f"MINIMUM {min_exp} years"
        exp_rule = (
            f"The role requires at least {min_exp} years of experience. "
            f"Candidates with fewer than {min_exp} years should receive a significantly "
            f"lower score (reduce by 20–30 points). Candidates with much more experience "
            f"than needed may also be overqualified — use judgment."
        )

    for candidate in candidates:
        try:
            prompt = f"""
You are an expert recruiter screening candidates for the following job.

JOB TITLE: {job.title}
JOB DESCRIPTION: {job.description}
REQUIRED SKILLS: {job.required_skills}
EXPERIENCE REQUIRED: {exp_requirement}

EXPERIENCE RULE (follow strictly):
{exp_rule}

CANDIDATE PROFILE:
Name: {candidate.full_name}
Skills: {candidate.skills}
Experience: {candidate.experience_years} years
Education: {candidate.education}
Work History: {candidate.work_history}

Score this candidate from 0 to 100 based on:
- Skills match with required skills (40%)
- Experience fit — penalise heavily if outside required range (30%)
- Education relevance (15%)
- Overall profile quality (15%)

If experience is outside the required range, you MUST flag it in red_flags.

Return ONLY this JSON, no markdown, no explanation:
{{
    "match_score": 0-100,
    "justification": "2-3 sentence explanation including experience assessment",
    "red_flags": "mention if experience is too low, too high, or null if experience fits perfectly",
    "skills_matched": "comma-separated required skills the candidate has",
    "skills_missing": "comma-separated required skills the candidate lacks"
}}
"""

            response = await get_scoring_response(prompt)
            clean = response.strip().replace("```json", "").replace("```", "").strip()
            result = json.loads(clean)

            raw_score = result.get("match_score", 0)

            # ── Hard experience penalty (post-LLM safety net) ──────────────
            # LLMs sometimes ignore instructions. This enforces the penalty
            # mathematically as a backstop.
            cand_exp = candidate.experience_years or 0
            exp_penalty = 0
            exp_flag = None

            if max_exp > 0 and cand_exp > max_exp:
                # Overqualified
                overshoot = cand_exp - max_exp
                exp_penalty = min(35, overshoot * 7)
                exp_flag = f"Overqualified: {cand_exp} yrs experience exceeds the {min_exp}–{max_exp} yr requirement."
            elif min_exp > 0 and cand_exp < min_exp:
                # Under-experienced
                shortfall = min_exp - cand_exp
                exp_penalty = min(35, shortfall * 8)
                exp_flag = f"Under-experienced: {cand_exp} yrs experience is below the {min_exp} yr minimum."
            elif min_exp == 0 and max_exp == 0 and cand_exp >= 3:
                # Fresher role — anyone with 3+ years is overqualified
                exp_penalty = min(25, (cand_exp - 2) * 6)
                exp_flag = f"Overqualified for fresher role: {cand_exp} yrs experience."

            final_score = max(0, min(100, raw_score - exp_penalty))

            # Merge exp_flag into red_flags
            existing_flags = result.get("red_flags") or ""
            if exp_flag:
                red_flags = f"{exp_flag} {existing_flags}".strip() if existing_flags and existing_flags.lower() != "null" else exp_flag
            else:
                red_flags = existing_flags if existing_flags and existing_flags.lower() != "null" else None

            scored.append({
                "candidate_id":    candidate.id,
                "full_name":       candidate.full_name,
                "match_score":     final_score,
                "justification":   result.get("justification", ""),
                "red_flags":       red_flags,
                "skills_matched":  result.get("skills_matched", ""),
                "skills_missing":  result.get("skills_missing", ""),
                "experience_years": cand_exp,
                "experience_flag": bool(exp_flag),
                "linkedin_url":    candidate.linkedin_url,
                "github_url":      candidate.github_url,
            })
            print(f"  ✓ Scored {candidate.full_name}: {final_score}% (raw {raw_score}%, exp penalty -{exp_penalty})")

        except Exception as e:
            print(f"  ✗ Failed to score {candidate.full_name}: {e}")
            scored.append({
                "candidate_id": candidate.id,
                "full_name":    candidate.full_name,
                "match_score":  0,
                "justification": "Scoring failed due to parsing error.",
                "red_flags":    "CV could not be parsed correctly.",
                "linkedin_url": candidate.linkedin_url,
                "github_url":   candidate.github_url,
            })

    return scored


async def stage_verify_profiles

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
