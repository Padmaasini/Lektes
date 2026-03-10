from sqlalchemy import Column, String, Text, DateTime, Integer
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.core.database import Base

class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    required_skills = Column(Text, nullable=True)       # comma separated
    nice_to_have_skills = Column(Text, nullable=True)   # comma separated
    min_experience_years = Column(Integer, default=0)   # 0 = fresher / any
    max_experience_years = Column(Integer, default=0)   # 0 = no upper limit
    hr_email = Column(String(255), nullable=False)
    status = Column(String(50), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    candidates = relationship("Candidate", back_populates="job", cascade="all, delete-orphan")
    screenings = relationship("Screening", back_populates="job", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Job {self.title}>"
