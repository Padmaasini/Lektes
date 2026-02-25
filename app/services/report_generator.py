from typing import List
from app.models.candidate import Candidate
from app.models.job import Job

async def generate_report(job: Job, candidates: List[Candidate]) -> dict:
    """
    Generate a structured report from screened candidates.
    Returns a ranked list of top candidates with scores and justifications.
    """
    report = {
        "job_title": job.title,
        "job_id": job.id,
        "hr_email": job.hr_email,
        "total_candidates": len(candidates),
        "top_candidates": [
            {
                "rank": idx + 1,
                "name": c.full_name or "Unknown",
                "email": c.email or "—",
                "match_score": round(c.match_score or 0, 1),
                "match_percentage": f"{round(c.match_score or 0, 1)}%",
                "skills": c.skills or "—",
                "experience_years": c.experience_years or 0,
                "justification": c.score_justification or "—",
                "red_flags": c.red_flags or None,
                "linkedin_url": c.linkedin_url or None,
                "github_url": c.github_url or None,
            }
            for idx, c in enumerate(candidates)
        ]
    }
    return report
