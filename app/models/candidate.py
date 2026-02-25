from sqlalchemy import Column, String, Text, DateTime, Float, ForeignKey, Integer
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.core.database import Base

class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)

    # Basic Info (extracted from CV)
    full_name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    location = Column(String(255), nullable=True)

    # CV Data
    cv_file_path = Column(String(500), nullable=True)
    cv_raw_text = Column(Text, nullable=True)
    skills = Column(Text, nullable=True)            # comma separated
    experience_years = Column(Float, default=0)
    education = Column(Text, nullable=True)
    work_history = Column(Text, nullable=True)      # JSON string

    # External Profiles
    linkedin_url = Column(String(500), nullable=True)
    github_url = Column(String(500), nullable=True)
    kaggle_url = Column(String(500), nullable=True)
    portfolio_url = Column(String(500), nullable=True)

    # Verification Data
    linkedin_verified = Column(Text, nullable=True)  # JSON string
    github_verified = Column(Text, nullable=True)    # JSON string

    # Scoring
    match_score = Column(Float, nullable=True)       # 0 to 100
    rank = Column(Integer, nullable=True)
    score_justification = Column(Text, nullable=True)
    red_flags = Column(Text, nullable=True)

    # Source
    source = Column(String(100), default="manual_upload")  # linkedin, portal, manual

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    job = relationship("Job", back_populates="candidates")

    def __repr__(self):
        return f"<Candidate {self.full_name} - Score: {self.match_score}>"
