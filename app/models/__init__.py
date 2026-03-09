# Import all models here so SQLAlchemy creates all tables on init_db()
from app.models.job import Job
from app.models.candidate import Candidate
from app.models.screening import Screening
from app.models.feedback import Feedback