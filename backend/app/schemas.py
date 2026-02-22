from typing import List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime

class WipeEvent(BaseModel):
    t: datetime
    cells: List[List[int]]  # [[r,c], [r,c], ...]

class SessionIngestPayload(BaseModel):
    session_id: str
    surface_id: str
    surface_type: str
    room_id: Optional[str] = None
    cleaner_id: Optional[str] = None

    start_time: datetime
    end_time: datetime

    grid_h: int
    grid_w: int

    coverage_count_grid: List[List[int]]
    high_touch_mask: Optional[List[List[int]]] = None

    wipe_events: Optional[List[WipeEvent]] = None
    camera_id: Optional[str] = None


class SessionSummaryOut(BaseModel):
    session_id: str

    quality_score: float
    coverage_percent: float
    high_touch_coverage_percent: Optional[float]

    overwipe_ratio: float
    uniformity_std: float
    wipe_events_count: Optional[int]

    missed_cells: List[dict]
    flags: List[str]

    cluster_name: Optional[str] = None
    risk_prob: Optional[float] = None
    risk_factors: Optional[Any] = None