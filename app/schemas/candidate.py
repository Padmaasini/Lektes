from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class CandidateResponse(BaseModel):
    id: str
    job_id: str
    full_name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    location: Optional[str]
    skills: Optional[str]
    experience_years: Optional[float]
    education: Optional[str]
    linkedin_url: Optional[str]
    github_url: Optional[str]
    kaggle_url: Optional[str]
    match_score: Optional[float]
    rank: Optional[int]
    score_justification: Optional[str]
    red_flags: Optional[str]
    source: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
