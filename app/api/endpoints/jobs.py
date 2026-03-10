from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
from app.core.database import get_db
from app.models.job import Job
from app.schemas.job import JobCreate, JobResponse

router = APIRouter()


# ── PARSE JOB AD ─────────────────────────────────────────────────────────────

class ParseRequest(BaseModel):
    raw_text: str

@router.post("/parse")
async def parse_job_ad(req: ParseRequest):
    """
    Extract structured fields from raw job posting text using the LLM.
    Accepts any format: LinkedIn posts, company portals, plain text.
    Returns: title, description, required_skills, nice_to_have_skills,
             min_experience_years, max_experience_years.
    """
    text = req.raw_text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="No text provided.")

    import json, re
    from app.services.llm_service import get_llm_response

    prompt = f"""Extract the key details from the following job posting and return ONLY a valid JSON object.

JOB POSTING:
{text[:4000]}

Return this exact JSON structure (no markdown, no explanation):
{{
    "title": "job title",
    "description": "2-4 sentence summary of the role and main responsibilities",
    "required_skills": "comma-separated list of required technical skills",
    "nice_to_have_skills": "comma-separated list of preferred/nice-to-have skills, or empty string",
    "min_experience_years": 0,
    "max_experience_years": 0
}}

Rules:
- min_experience_years: the minimum years of experience required (0 if entry-level or not stated)
- max_experience_years: the maximum years required (0 if no upper limit stated)
- required_skills: only hard technical skills (e.g. Python, SQL, Azure) — not soft skills
- nice_to_have_skills: skills listed as preferred, bonus, or nice to have
- description: keep it concise and factual, based only on the posting
"""

    try:
        response = await get_llm_response(prompt)
        clean = response.strip()
        clean = re.sub(r"^```(?:json)?", "", clean, flags=re.MULTILINE).strip()
        clean = re.sub(r"```$", "", clean, flags=re.MULTILINE).strip()

        # Find the JSON object if there's surrounding text
        if not clean.startswith("{"):
            start = clean.find("{")
            end   = clean.rfind("}")
            if start != -1 and end != -1:
                clean = clean[start:end + 1]

        parsed = json.loads(clean)

        # Ensure all expected fields exist with sane defaults
        return {
            "title":                parsed.get("title", "").strip(),
            "description":          parsed.get("description", "").strip(),
            "required_skills":      parsed.get("required_skills", "").strip(),
            "nice_to_have_skills":  parsed.get("nice_to_have_skills", "").strip(),
            "min_experience_years": int(parsed.get("min_experience_years") or 0),
            "max_experience_years": int(parsed.get("max_experience_years") or 0),
        }

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=422, detail=f"Could not parse LLM response as JSON: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parsing failed: {str(e)}")



@router.post("/", response_model=JobResponse, status_code=201)
async def create_job(job: JobCreate, db: Session = Depends(get_db)):
    """
    Create a new job screening session.
    This is your starting point — every candidate is linked to a job.
    """
    db_job = Job(
        title=job.title,
        description=job.description,
        required_skills=",".join(job.required_skills) if job.required_skills else "",
        nice_to_have_skills=",".join(job.nice_to_have_skills) if job.nice_to_have_skills else "",
        min_experience_years=job.min_experience_years or 0,
        max_experience_years=job.max_experience_years or 0,
        hr_email=job.hr_email
    )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    return db_job

@router.get("/", response_model=List[JobResponse])
async def list_jobs(db: Session = Depends(get_db)):
    """List all active job screening sessions."""
    return db.query(Job).all()

@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, db: Session = Depends(get_db)):
    """Get a specific job by ID."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

import os as _os

@router.delete("/{job_id}", status_code=204)
async def delete_job(job_id: str, db: Session = Depends(get_db)):
    """Delete a job and all associated candidates and CV files."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Delete CV files from disk before ORM cascade
    from app.models.candidate import Candidate
    candidates = db.query(Candidate).filter(Candidate.job_id == job_id).all()
    for c in candidates:
        if c.cv_file_path and _os.path.exists(c.cv_file_path):
            try:
                _os.remove(c.cv_file_path)
            except OSError:
                pass

    db.delete(job)   # cascade="all, delete-orphan" removes candidates + screenings
    db.commit()
