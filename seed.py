from backend.services.database import SessionLocal, engine, Base
from backend.models.db_models import JobPostingORM
from backend.features.matching.scorer import get_model

Base.metadata.create_all(bind=engine)

db = SessionLocal()


model = get_model()

title = "Python Developer"
description = "Amazing job opportunity"
skills = ["python", "fastapi"]
text_to_embed = f"{title} {description} {' '.join(skills)}"


job_embedding = model.encode(text_to_embed).tolist()

sample_job = JobPostingORM(
    job_id="job_1",
    title=title,
    company="Tech Solutions",
    required_skills=skills,
    min_experience=2,
    description=description,
    location="Cairo",
    work_type="Full-time",
    salary=15000,
    embedding=job_embedding  
)

db.merge(sample_job)
db.commit()
db.close()

print("✅ Tables created and sample job added with precomputed embedding successfully!")