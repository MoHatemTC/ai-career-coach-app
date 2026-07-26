from sqlalchemy import Column, String, Integer, JSON
from pgvector.sqlalchemy import Vector  
from backend.services.database import Base
from backend.models.job_posting import JobPosting

class JobPostingORM(Base):
    __tablename__ = "job_postings"

    job_id = Column(String, primary_key=True, index=True)
    title = Column(String)
    company = Column(String)
    required_skills = Column(JSON, default=[])
    min_experience = Column(Integer, default=0)
    description = Column(String, default="")
    location = Column(String, default="")
    work_type = Column(String, default="")
    salary = Column(Integer, default=0)
    
    embedding = Column(Vector(384), nullable=True)

class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    status = Column(String, default="completed")

def orm_to_job_posting(orm_obj: JobPostingORM) -> JobPosting:
    return JobPosting(
        job_id=orm_obj.job_id,
        title=orm_obj.title,
        company=orm_obj.company,
        required_skills=orm_obj.required_skills or [],
        min_experience=orm_obj.min_experience or 0,
        description=orm_obj.description or "",
        location=orm_obj.location or "",
        work_type=orm_obj.work_type or "",
        salary=orm_obj.salary or 0
      
    )