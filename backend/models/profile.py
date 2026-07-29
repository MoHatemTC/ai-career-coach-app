from sqlalchemy import Column, Integer, String, Text
from backend.database import Base


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String)
    email = Column(String)
    phone = Column(String)

    headline = Column(String)
    location = Column(String)

    skills = Column(Text)
    education = Column(Text)
    experience = Column(Text)

    summary = Column(Text)

    # Added for matching / skill-gap compatibility
    target_role = Column(String, nullable=True)
    experience_level = Column(String, nullable=True)

    @property
    def user_id(self):
        return str(self.id)