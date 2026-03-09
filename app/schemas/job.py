from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class JobCreate(BaseModel):
    title: str
    description: str
    required_skills: Optional[List[str]] = []
    nice_to_have_skills: Optional[List[str]] = []
    min_experience_years: Optional[int] = 0   # 0 = fresher / any level
    max_experience_years: Optional[int] = 0   # 0 = no upper limit
    hr_email: str

class JobResponse(BaseModel):
    id: str
    title: str
    description: str
    required_skills: Optional[str]
    nice_to_have_skills: Optional[str]
    min_experience_years: int
    max_experience_years: int
    hr_email: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
