from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import SessionLocal
from models import CleaningSession
from datetime import datetime

router = APIRouter(prefix="/cleaning", tags=["cleaning"])

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/session")
def submit_session(data: dict, db: Session = Depends(get_db)):
    """
    Submit a cleaning session from the phone (coverage data, Presage metrics, etc.)
    """
    try:
        session = CleaningSession(
            room_id=data.get("room_id"),
            coverage_percent=data.get("coverage_percent", 0.0),
            duration=data.get("duration", 0.0),
            stress_level=data.get("stress_level"),
            engagement_level=data.get("engagement_level"),
            timestamp=datetime.utcnow()
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return {
            "status": "success",
            "session_id": session.id,
            "message": "Cleaning session saved"
        }
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}