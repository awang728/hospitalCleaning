from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from sqlalchemy.orm import Session as OrmSession
from sqlalchemy import func

from pydantic import BaseModel

from .db import Base, engine, get_db
from .models import Session, SessionGrid, SessionMetrics
from .schemas import SessionIngestPayload, SessionSummaryOut
from .analytics.pipeline import run_pipeline
from .routes_room_agg import router as room_agg_router
from .privacy import anon_id
from .security import require_ingest_key
from .snowflake_sync import push_summary
from .camera_stream import generate_frames, get_state, start_session, stop_session
import app.camera_stream as cs

app = FastAPI(title="Cleaning Analytics Backend")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

Base.metadata.create_all(bind=engine)
app.include_router(room_agg_router)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/cleansight", response_class=HTMLResponse)
def cleansight_page(request: Request):
    return templates.TemplateResponse("cleansight.html", {"request": request})


@app.post("/ingest/session")
def ingest_session(
    payload: SessionIngestPayload,
    db: OrmSession = Depends(get_db),
    _: None = Depends(require_ingest_key),
):
    duration_s = (payload.end_time - payload.start_time).total_seconds()
    if duration_s < 0:
        raise HTTPException(status_code=400, detail="end_time must be after start_time")

    if len(payload.coverage_count_grid) != payload.grid_h:
        raise HTTPException(status_code=400, detail="coverage_count_grid height != grid_h")
    if any(len(row) != payload.grid_w for row in payload.coverage_count_grid):
        raise HTTPException(status_code=400, detail="coverage_count_grid width != grid_w")

    if payload.high_touch_mask is not None:
        if len(payload.high_touch_mask) != payload.grid_h or any(
            len(row) != payload.grid_w for row in payload.high_touch_mask
        ):
            raise HTTPException(status_code=400, detail="high_touch_mask shape must match grid_h x grid_w")

    payload.cleaner_id = anon_id(payload.cleaner_id)

    existing = db.get(Session, payload.session_id)
    if existing:
        raise HTTPException(status_code=409, detail="session_id already exists")

    s = Session(
        session_id=payload.session_id,
        surface_id=payload.surface_id,
        surface_type=payload.surface_type,
        room_id=payload.room_id,
        cleaner_id=payload.cleaner_id,
        start_time=payload.start_time,
        end_time=payload.end_time,
        duration_s=duration_s,
        grid_h=payload.grid_h,
        grid_w=payload.grid_w,
        camera_id=payload.camera_id,
    )
    db.add(s)

    g = SessionGrid(
        session_id=payload.session_id,
        coverage_count_grid=payload.coverage_count_grid,
        high_touch_mask=payload.high_touch_mask,
        wipe_events=[we.model_dump() for we in payload.wipe_events] if payload.wipe_events else None,
    )
    db.add(g)

    metrics = run_pipeline(
        coverage_count_grid=payload.coverage_count_grid,
        high_touch_mask=payload.high_touch_mask,
        wipe_events=[we.model_dump() for we in payload.wipe_events] if payload.wipe_events else None,
        duration_s=duration_s,
        overwipe_threshold=3,
    )

    m = SessionMetrics(
        session_id=payload.session_id,
        coverage_percent=metrics["coverage_percent"],
        high_touch_coverage_percent=metrics["high_touch_coverage_percent"],
        overwipe_ratio=metrics["overwipe_ratio"],
        uniformity_std=metrics["uniformity_std"],
        wipe_events_count=metrics["wipe_events_count"],
        quality_score=metrics["quality_score"],
        missed_cells=metrics["missed_cells"],
        flags=metrics["flags"],
        cluster_label=metrics["cluster_label"],
        cluster_name=metrics["cluster_name"],
        risk_prob=metrics["risk_prob"],
        risk_factors=metrics["risk_factors"],
    )
    db.add(m)
    db.commit()

    try:
        push_summary(
            summary={
                "session_id": payload.session_id,
                "quality_score": metrics["quality_score"],
                "coverage_percent": metrics["coverage_percent"],
                "overwipe_ratio": metrics["overwipe_ratio"],
                "uniformity_std": metrics["uniformity_std"],
                "flags": metrics["flags"],
            },
            room_id=payload.room_id,
            surface_type=payload.surface_type,
        )
    except Exception as e:
        print("Snowflake sync failed:", e)

    return {"status": "ok", "session_id": payload.session_id, "quality_score": metrics["quality_score"]}


# -----------------------
# Frontend pages
# -----------------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


# -----------------------
# Camera stream
# -----------------------

@app.get("/video_feed")
def video_feed():
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.post("/camera/start")
def camera_start():
    if not cs._preview_boxes:
        return {"ok": False, "reason": "No surface detected yet"}
    ok = start_session((480, 640), cs._preview_boxes)
    return {"ok": ok}


@app.post("/camera/stop")
def camera_stop():
    ok = stop_session()
    return {"ok": ok}


# -----------------------
# Analytics
# -----------------------

@app.get("/analytics/summary")
def analytics_summary(db: OrmSession = Depends(get_db)):
    total_sessions = db.query(Session).count()
    if total_sessions == 0:
        return {"average_coverage_percent": 0.0, "total_sessions": 0}
    avg_cov = db.query(func.avg(SessionMetrics.coverage_percent)).scalar() or 0.0
    return {
        "average_coverage_percent": float(avg_cov),
        "total_sessions": int(total_sessions),
    }


@app.get("/analytics/live")
def analytics_live():
    state = get_state()
    return {
        "coverage_percent": state["coverage_percent"],
        "high_touch_done": state["high_touch_done"],
        "recording": state["recording"],
    }


class AISummaryIn(BaseModel):
    room_id: str
    coverage_percent: float
    duration: int
    stress_level: float | None = None


@app.post("/ai/summary")
def ai_summary(payload: AISummaryIn):
    msg = (
        f"Room: {payload.room_id}\n"
        f"Coverage: {payload.coverage_percent}%\n"
        f"Duration: {payload.duration}s\n"
    )
    if payload.stress_level is not None:
        msg += f"Stress: {payload.stress_level}\n"
    msg += "\nRecommendation: Prioritize edges/corners and slow down slightly to improve uniformity."
    return {"summary": msg}


# -----------------------
# All sessions (for cleansight dashboard auto-load)
# -----------------------

@app.get("/sessions/all")
def get_all_sessions(db: OrmSession = Depends(get_db)):
    sessions = db.query(Session).order_by(Session.created_at.desc()).all()
    result = []
    for s in sessions:
        grid = db.get(SessionGrid, s.session_id)
        if not grid:
            continue
        result.append({
            "session_id": s.session_id,
            "surface_id": s.surface_id,
            "surface_type": s.surface_type,
            "room_id": s.room_id or "UNKNOWN",
            "cleaner_id": s.cleaner_id or "anon",
            "start_time": s.start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_time": s.end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "grid_h": s.grid_h,
            "grid_w": s.grid_w,
            "camera_id": s.camera_id or "CAM_01",
            "coverage_count_grid": grid.coverage_count_grid,
            "high_touch_mask": grid.high_touch_mask or [[0]*s.grid_w for _ in range(s.grid_h)],
            "wipe_events": grid.wipe_events or [],
            "_label": f"{s.room_id or 'Room'} · {s.surface_type}",
        })
    return result


# -----------------------
# Per-session summary
# -----------------------

@app.get("/sessions/{session_id}/summary", response_model=SessionSummaryOut)
def session_summary(session_id: str, db: OrmSession = Depends(get_db)):
    s = db.get(Session, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="session not found")
    m = db.get(SessionMetrics, session_id)
    if not m:
        raise HTTPException(status_code=404, detail="metrics not found")
    return SessionSummaryOut(
        session_id=session_id,
        quality_score=m.quality_score,
        coverage_percent=m.coverage_percent,
        high_touch_coverage_percent=m.high_touch_coverage_percent,
        overwipe_ratio=m.overwipe_ratio,
        uniformity_std=m.uniformity_std,
        wipe_events_count=m.wipe_events_count,
        missed_cells=m.missed_cells,
        flags=m.flags,
        cluster_name=m.cluster_name,
        risk_prob=m.risk_prob,
        risk_factors=m.risk_factors,
    )