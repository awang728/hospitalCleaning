from database import SessionLocal
from models import CleaningSession
from datetime import datetime

db = SessionLocal()

demo_sessions = [
    {"room_id": "ICU-101", "coverage_percent": 78.5, "duration": 145, "stress_level": 0.72, "engagement_level": 0.65},
    {"room_id": "ER-205",  "coverage_percent": 92.0, "duration": 90,  "stress_level": 0.45, "engagement_level": 0.88},
    {"room_id": "ICU-101", "coverage_percent": 62.3, "duration": 180, "stress_level": 0.85, "engagement_level": 0.40},
    {"room_id": "OR-310",  "coverage_percent": 88.7, "duration": 110, "stress_level": 0.55, "engagement_level": 0.78},
    {"room_id": "ER-205",  "coverage_percent": 71.0, "duration": 160, "stress_level": 0.68, "engagement_level": 0.52},
]

for s in demo_sessions:
    session = CleaningSession(
        room_id=s["room_id"],
        coverage_percent=s["coverage_percent"],
        duration=s["duration"],
        stress_level=s["stress_level"],
        engagement_level=s["engagement_level"],
        timestamp=datetime.utcnow()
    )
    db.add(session)

db.commit()
db.close()

print("Added 5 demo cleaning sessions!")