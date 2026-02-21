from sqlalchemy import Column, Integer, Float, String, DateTime
from database import Base

class CleaningSession(Base):
    __tablename__ = "cleaning_sessions"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(String)
    coverage_percent = Column(Float)
    duration = Column(Float)
    stress_level = Column(Float)
    engagement_level = Column(Float)
    timestamp = Column(DateTime)

