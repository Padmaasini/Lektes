from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.core.database import Base

class Screening(Base):
    __tablename__ = "screenings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)
    status = Column(String(50), default="pending")  # pending, processing, completed, failed
    report_path = Column(String(500), nullable=True)
    report_sent = Column(String(5), default="false")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    job = relationship("Job", back_populates="screenings")

    def __repr__(self):
        return f"<Screening {self.id} - {self.status}>"
