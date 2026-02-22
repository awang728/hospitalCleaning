from __future__ import annotations
import numpy as np
from typing import Optional, Tuple

def _to_np(grid):
    return np.array(grid, dtype=float)

def compute_coverage_percent(coverage_count_grid) -> float:
    G = _to_np(coverage_count_grid)
    C = (G > 0).astype(float)
    return float(C.mean() * 100.0)

def compute_high_touch_coverage_percent(coverage_count_grid, high_touch_mask) -> Optional[float]:
    if high_touch_mask is None:
        return None
    G = _to_np(coverage_count_grid)
    C = (G > 0).astype(float)
    M = _to_np(high_touch_mask)
    denom = M.sum()
    if denom <= 0:
        return None
    return float(((C * M).sum() / denom) * 100.0)

def compute_overwipe_ratio(coverage_count_grid, overwipe_threshold: int = 3) -> float:
    G = _to_np(coverage_count_grid)
    O = (G >= overwipe_threshold).astype(float)
    return float(O.mean())

def compute_uniformity_std(coverage_count_grid) -> float:
    G = _to_np(coverage_count_grid)
    return float(G.std())

def count_wipe_events(wipe_events) -> Optional[int]:
    if wipe_events is None:
        return None
    return int(len(wipe_events))