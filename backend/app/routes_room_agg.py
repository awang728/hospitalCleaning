from typing import Optional, Dict, Tuple, List
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy import desc

# NOTE: adjust these imports to match your project structure if different
from .db import get_db
from .models import Session, SessionGrid  # assumes you have these ORM models

router = APIRouter(tags=["room-analytics"])


def _np_grid(grid: List[List[int]]) -> np.ndarray:
    return np.array(grid, dtype=int)


def _get_sessions(db: OrmSession, room_id: str, surface_type: str, n: int):
    q = db.query(Session).filter(Session.room_id == room_id, Session.surface_type == surface_type)

    # sort newest-first
    if hasattr(Session, "end_time"):
        q = q.order_by(desc(Session.end_time))
    elif hasattr(Session, "start_time"):
        q = q.order_by(desc(Session.start_time))

    return q.limit(n).all()


@router.get("/rooms/{room_id}/most_touched")
def most_touched(
    room_id: str,
    surface_type: str = Query(..., description="Required. E.g. tray, bedrail, handle."),
    n_sessions: int = Query(50, ge=1, le=500),
    k: int = Query(20, ge=1, le=500),
    db: OrmSession = Depends(get_db),
):
    sessions = _get_sessions(db, room_id, surface_type, n_sessions)
    if not sessions:
        raise HTTPException(status_code=404, detail="no sessions found for room+surface_type")

    grids = []
    for s in sessions:
        g = db.get(SessionGrid, s.session_id)
        if g and g.coverage_count_grid:
            grids.append(_np_grid(g.coverage_count_grid))

    if not grids:
        raise HTTPException(status_code=404, detail="no grids found for those sessions")

    shape = grids[0].shape
    grids = [G for G in grids if G.shape == shape]
    H, W = shape

    agg = np.zeros((H, W), dtype=int)
    for G in grids:
        agg += G

    items = [{"r": r, "c": c, "touch_count": int(agg[r, c])} for r in range(H) for c in range(W)]
    items.sort(key=lambda x: x["touch_count"], reverse=True)

    return {
        "room_id": room_id,
        "surface_type": surface_type,
        "sessions_found": len(sessions),
        "sessions_used": len(grids),
        "grid_h": H,
        "grid_w": W,
        "top_touched": items[:k],
    }


@router.get("/rooms/{room_id}/most_disregarded")
def most_disregarded(
    room_id: str,
    surface_type: str = Query(..., description="Required. E.g. tray, bedrail, handle."),
    n_sessions: int = Query(50, ge=1, le=500),
    k: int = Query(20, ge=1, le=500),
    db: OrmSession = Depends(get_db),
):
    sessions = _get_sessions(db, room_id, surface_type, n_sessions)
    if not sessions:
        raise HTTPException(status_code=404, detail="no sessions found for room+surface_type")

    # Definition: "disregarded" = cell untouched (count == 0) in a session.
    # We count how many sessions each cell was missed in.
    miss_freq: Dict[Tuple[int, int], int] = {}
    used = 0
    shape = None

    for s in sessions:
        g = db.get(SessionGrid, s.session_id)
        if not g or not g.coverage_count_grid:
            continue

        G = _np_grid(g.coverage_count_grid)
        if shape is None:
            shape = G.shape
        if G.shape != shape:
            continue  # skip mismatched shapes

        used += 1
        zeros = (G == 0)
        for r in range(G.shape[0]):
            for c in range(G.shape[1]):
                if zeros[r, c]:
                    miss_freq[(r, c)] = miss_freq.get((r, c), 0) + 1

    if not miss_freq:
        raise HTTPException(status_code=404, detail="no missed cells found (or no usable grids)")

    H, W = shape
    items = [{"r": r, "c": c, "miss_sessions": int(cnt)} for (r, c), cnt in miss_freq.items()]
    items.sort(key=lambda x: x["miss_sessions"], reverse=True)

    return {
        "room_id": room_id,
        "surface_type": surface_type,
        "sessions_found": len(sessions),
        "sessions_used": used,
        "grid_h": H,
        "grid_w": W,
        "top_disregarded": items[:k],
    }


@router.get("/rooms/{room_id}/overwiped_hotspots")
def overwiped_hotspots(
    room_id: str,
    surface_type: str = Query(..., description="Required. E.g. tray, bedrail, handle."),
    n_sessions: int = Query(50, ge=1, le=500),
    k: int = Query(20, ge=1, le=500),
    threshold: int = Query(3, ge=1, le=100, description="Cell count >= threshold counts as overwiped for that session."),
    db: OrmSession = Depends(get_db),
):
    sessions = _get_sessions(db, room_id, surface_type, n_sessions)
    if not sessions:
        raise HTTPException(status_code=404, detail="no sessions found for room+surface_type")

    freq: Dict[Tuple[int, int], int] = {}
    used = 0
    shape = None

    for s in sessions:
        g = db.get(SessionGrid, s.session_id)
        if not g or not g.coverage_count_grid:
            continue

        G = _np_grid(g.coverage_count_grid)
        if shape is None:
            shape = G.shape
        if G.shape != shape:
            continue

        used += 1
        mask = (G >= threshold)
        for r in range(G.shape[0]):
            for c in range(G.shape[1]):
                if mask[r, c]:
                    freq[(r, c)] = freq.get((r, c), 0) + 1

    H, W = shape if shape else (None, None)

    items = [{"r": r, "c": c, "overwipe_sessions": int(cnt)} for (r, c), cnt in freq.items()]
    items.sort(key=lambda x: x["overwipe_sessions"], reverse=True)

    return {
        "room_id": room_id,
        "surface_type": surface_type,
        "threshold": threshold,
        "sessions_found": len(sessions),
        "sessions_used": used,
        "grid_h": H,
        "grid_w": W,
        "top_overwiped": items[:k],
    }