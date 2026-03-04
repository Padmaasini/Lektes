from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from app.core.database import get_db
from app.models.job import Job
from app.models.candidate import Candidate
from app.schemas.job import JobCreate, JobResponse

router = APIRouter()


class ParseJobRequest(BaseModel):
    raw_text: str

class ParseJobResponse(BaseModel):
    title: str
    description: str
    required_skills: str
    nice_to_have_skills: Optional[str] = None
    min_experience_years: int = 0


@router.post("/parse", response_model=ParseJobResponse)
async def parse_job_posting(req: ParseJobRequest):
    """
    Extract structured job details from raw job posting text.
    Accepts any format — LinkedIn posts, portal exports, plain text.
    Uses Groq LLM to extract title, skills, experience requirements.
    """
    from app.services.llm_service import get_llm_response
    import json

    prompt = f"""Extract structured job details from this job posting.
Return ONLY valid JSON, no markdown, no backticks, no explanation.

JOB POSTING TEXT:
{req.raw_text[:3000]}

Return this exact JSON:
{{
  "title": "exact job title",
  "description": "2-3 sentence summary of the role and responsibilities",
  "required_skills": "comma separated list of required technical skills",
  "nice_to_have_skills": "comma separated list of preferred/bonus skills or null",
  "min_experience_years": 3
}}

Rules:
- title: extract the exact job title, not a paraphrase
- required_skills: only hard requirements, comma separated string
- nice_to_have_skills: only explicitly stated preferred/bonus skills
- min_experience_years: integer years, 0 if not stated
- Return ONLY the JSON object"""

    try:
        response = await get_llm_response(prompt)
        clean = response.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()
        parsed = json.loads(clean)
        return ParseJobResponse(
            title                = parsed.get("title", ""),
            description          = parsed.get("description", ""),
            required_skills      = parsed.get("required_skills", ""),
            nice_to_have_skills  = parsed.get("nice_to_have_skills"),
            min_experience_years = int(parsed.get("min_experience_years") or 0),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not parse job posting: {str(e)}")


@router.post("/", response_model=JobResponse, status_code=201)
async def create_job(job: JobCreate, db: Session = Depends(get_db)):
    """Create a new job screening session."""
    db_job = Job(
        title=job.title,
        description=job.description,
        required_skills=",".join(job.required_skills) if job.required_skills else "",
        nice_to_have_skills=",".join(job.nice_to_have_skills) if job.nice_to_have_skills else "",
        min_experience_years=job.min_experience_years,
        hr_email=job.hr_email
    )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    return db_job

@router.get("/", response_model=List[JobResponse])
async def list_jobs(db: Session = Depends(get_db)):
    """List all job screening sessions."""
    return db.query(Job).order_by(Job.created_at.desc()).all()

@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, db: Session = Depends(get_db)):
    """Get a specific job by ID."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.delete("/{job_id}", status_code=204)
async def delete_job(job_id: str, db: Session = Depends(get_db)):
    """Delete a job and all its candidates."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    db.delete(job)
    db.commit()

@router.delete("/", status_code=200)
async def delete_all_jobs(db: Session = Depends(get_db)):
    """Delete ALL jobs and candidates — full database reset."""
    candidate_count = db.query(Candidate).count()
    job_count = db.query(Job).count()
    db.query(Candidate).delete()
    db.query(Job).delete()
    db.commit()
    return {
        "message": "All data cleared successfully",
        "jobs_deleted": job_count,
        "candidates_deleted": candidate_count
    }
