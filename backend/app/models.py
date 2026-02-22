from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import relationship
from .db import Base

class Session(Base):
    __tablename__ = "sessions"

    session_id = Column(String, primary_key=True, index=True)
    surface_id = Column(String, nullable=False, index=True)
    surface_type = Column(String, nullable=False, index=True)
    room_id = Column(String, nullable=True, index=True)
    cleaner_id = Column(String, nullable=True, index=True)

    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    duration_s = Column(Float, nullable=False)

    grid_h = Column(Integer, nullable=False)
    grid_w = Column(Integer, nullable=False)

    camera_id = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    grid = relationship("SessionGrid", back_populates="session", uselist=False, cascade="all, delete-orphan")
    metrics = relationship("SessionMetrics", back_populates="session", uselist=False, cascade="all, delete-orphan")


class SessionGrid(Base):
    __tablename__ = "session_grids"

    session_id = Column(String, ForeignKey("sessions.session_id", ondelete="CASCADE"), primary_key=True)
    coverage_count_grid = Column(JSON, nullable=False)
    high_touch_mask = Column(JSON, nullable=True)

    wipe_events = Column(JSON, nullable=True)  # optional: list of events

    session = relationship("Session", back_populates="grid")


class SessionMetrics(Base):
    __tablename__ = "session_metrics"

    session_id = Column(String, ForeignKey("sessions.session_id", ondelete="CASCADE"), primary_key=True)

    coverage_percent = Column(Float, nullable=False)
    high_touch_coverage_percent = Column(Float, nullable=True)

    overwipe_ratio = Column(Float, nullable=False)
    uniformity_std = Column(Float, nullable=False)
    wipe_events_count = Column(Integer, nullable=True)

    quality_score = Column(Float, nullable=False)

    missed_cells = Column(JSON, nullable=False)     # list of {r,c,priority}
    flags = Column(JSON, nullable=False)            # list of strings

    # placeholders for later ML
    cluster_label = Column(Integer, nullable=True)
    cluster_name = Column(String, nullable=True)
    risk_prob = Column(Float, nullable=True)
    risk_factors = Column(JSON, nullable=True)

    session = relationship("Session", back_populates="metrics")