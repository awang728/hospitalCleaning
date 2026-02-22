from __future__ import annotations
from typing import Optional, List, Tuple

def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))

def compute_quality_score(
    coverage_percent: float,
    high_touch_coverage_percent: Optional[float],
    overwipe_ratio: float,
    uniformity_std: float,
    duration_s: float,
) -> Tuple[float, List[str]]:
    flags: List[str] = []

    coverage_score = clamp(coverage_percent / 100.0)

    if high_touch_coverage_percent is None:
        high_touch_score = coverage_score
        flags.append("no_high_touch_mask")
    else:
        high_touch_score = clamp(high_touch_coverage_percent / 100.0)

    # overwipe: assume >20% of cells overwiped is really bad
    overwipe_score = clamp(1.0 - (overwipe_ratio / 0.20))

    # uniformity: lower std is better; this is a simple MVP mapping.
    # If std >= 5, uniformity score ~0; if std ~0, score ~1.
    uniformity_score = clamp(1.0 - (uniformity_std / 5.0))

    # rushing penalty
    rushing_penalty = 0.0
    if duration_s < 30 and coverage_percent < 70:
        rushing_penalty = 15.0
        flags.append("rushed")

    if high_touch_coverage_percent is not None and high_touch_coverage_percent < 70:
        flags.append("missed_high_touch")

    if overwipe_ratio > 0.10:
        flags.append("overwiping")

    raw = 100.0 * (
        0.35 * coverage_score +
        0.35 * high_touch_score +
        0.15 * overwipe_score +
        0.15 * uniformity_score
    )

    quality = max(0.0, min(100.0, raw - rushing_penalty))
    return float(quality), flags