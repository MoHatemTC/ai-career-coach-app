from backend.services.database import SessionLocal, engine, Base
from backend.models.db_models import JobPostingORM

Base.metadata.create_all(bind=engine)

db = SessionLocal()

sample_job = JobPostingORM(
    job_id="job_1",
    title="Python Developer",
    company="Tech Solutions",
    required_skills=["python", "fastapi"],
    min_experience=2,
    description="Amazing job opportunity",
    location="Cairo",
    work_type="Full-time",
    salary=15000
)

db.merge(sample_job)
db.commit()
db.close()

print("✅ Tables created and sample job added successfully!")