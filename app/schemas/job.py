from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime

class JobCreate(BaseModel):
    title: str
    description: str
    required_skills: Optional[List[str]] = []
    nice_to_have_skills: Optional[List[str]] = []
    min_experience_years: Optional[int] = 0
    hr_email: str

    class Config:
        json_schema_extra = {
            "example": {
                "title": "Senior Python Developer",
                "description": "We are looking for a senior Python developer with FastAPI experience...",
                "required_skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
                "nice_to_have_skills": ["Redis", "Kubernetes", "AWS"],
                "min_experience_years": 3,
                "hr_email": "hr@company.com"
            }
        }

class JobResponse(BaseModel):
    id: str
    title: str
    description: str
    required_skills: Optional[str]
    nice_to_have_skills: Optional[str]
    min_experience_years: int
    hr_email: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
