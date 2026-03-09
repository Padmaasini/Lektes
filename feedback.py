"""
Feedback model — stores HR thumbs up/down on screened candidates.

This is the foundation of TalentMesh's learning engine.
Every decision captured here becomes training signal for:
  - Phase 2: per-company score weight calibration
  - Phase 3: vector similarity against past successful hires

Fields:
  - decision: "shortlist" (👍) or "reject" (👎)
  - outcome:  filled in later — "hired", "interviewed", "declined"
              Starts NULL, HR updates it post-interview
  - notes:    optional freetext — "great culture fit", "overqualified"
"""

from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.core.database import Base


class Feedback(Base):
    __tablename__ = "feedback"

    id           = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id = Column(String, ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    job_id       = Column(String, ForeignKey("jobs.id",       ondelete="CASCADE"), nullable=False)

    # HR decision at screening time: "shortlist" or "reject"
    decision     = Column(String(20), nullable=False)

    # Post-interview outcome — updated later by HR
    # Values: "hired" | "interviewed" | "declined" | None
    outcome      = Column(String(30), nullable=True)

    # Optional HR note
    notes        = Column(Text, nullable=True)

    # Who submitted the feedback (HR email from job record)
    submitted_by = Column(String(255), nullable=True)

    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    candidate    = relationship("Candidate", back_populates="feedback")

    def __repr__(self):
        return f"<Feedback candidate={self.candidate_id} decision={self.decision}>"
