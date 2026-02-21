from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import SessionLocal
from models import CleaningSession

router = APIRouter(prefix="/analytics", tags=["analytics"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    """
    Basic summary stats: average coverage, count of sessions, etc.
    """
    try:
        avg_coverage = db.query(func.avg(CleaningSession.coverage_percent)).scalar() or 0.0
        total_sessions = db.query(CleaningSession).count()
        high_stress_sessions = db.query(CleaningSession).filter(CleaningSession.stress_level > 0.7).count()

        return {
            "average_coverage_percent": round(avg_coverage, 2),
            "total_sessions": total_sessions,
            "high_stress_sessions": high_stress_sessions,
            "message": "Analytics summary"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}