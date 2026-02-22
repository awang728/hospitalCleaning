from __future__ import annotations
from typing import Dict, Any, Optional

from .metrics import (
    compute_coverage_percent,
    compute_high_touch_coverage_percent,
    compute_overwipe_ratio,
    compute_uniformity_std,
    count_wipe_events,
)
from .missed_zones import top_missed_cells
from .scoring import compute_quality_score

def run_pipeline(
    coverage_count_grid,
    high_touch_mask,
    wipe_events,
    duration_s: float,
    overwipe_threshold: int = 3,
) -> Dict[str, Any]:
    coverage_percent = compute_coverage_percent(coverage_count_grid)
    high_touch_cov = compute_high_touch_coverage_percent(coverage_count_grid, high_touch_mask)
    overwipe_ratio = compute_overwipe_ratio(coverage_count_grid, overwipe_threshold=overwipe_threshold)
    uniformity_std = compute_uniformity_std(coverage_count_grid)
    wipe_events_count = count_wipe_events(wipe_events)

    missed_cells = top_missed_cells(coverage_count_grid, high_touch_mask, k=15)

    quality_score, flags = compute_quality_score(
        coverage_percent=coverage_percent,
        high_touch_coverage_percent=high_touch_cov,
        overwipe_ratio=overwipe_ratio,
        uniformity_std=uniformity_std,
        duration_s=duration_s,
    )

    return {
        "coverage_percent": coverage_percent,
        "high_touch_coverage_percent": high_touch_cov,
        "overwipe_ratio": overwipe_ratio,
        "uniformity_std": uniformity_std,
        "wipe_events_count": wipe_events_count,
        "quality_score": quality_score,
        "missed_cells": missed_cells,
        "flags": flags,
        # placeholders for later ML
        "cluster_label": None,
        "cluster_name": None,
        "risk_prob": None,
        "risk_factors": None,
    }