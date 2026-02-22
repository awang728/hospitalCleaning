from __future__ import annotations
import numpy as np
from typing import List, Optional

def top_missed_cells(
    coverage_count_grid,
    high_touch_mask: Optional[list] = None,
    k: int = 15
) -> List[dict]:
    G = np.array(coverage_count_grid, dtype=float)
    C = (G > 0).astype(int)          # 1 covered, 0 missed
    missed = (C == 0).astype(int)    # 1 missed

    H, W = missed.shape

    items = []

    if high_touch_mask is not None:
        M = np.array(high_touch_mask, dtype=int)
        missed_hi = missed * M
        hi_coords = np.argwhere(missed_hi == 1)
        for r, c in hi_coords:
            items.append({"r": int(r), "c": int(c), "priority": "high_touch"})

    # add normal missed cells if needed
    if len(items) < k:
        normal_coords = np.argwhere(missed == 1)
        # filter out ones already included as high_touch
        hi_set = {(d["r"], d["c"]) for d in items}
        for r, c in normal_coords:
            if (int(r), int(c)) in hi_set:
                continue
            items.append({"r": int(r), "c": int(c), "priority": "normal"})
            if len(items) >= k:
                break
    else:
        items = items[:k]

    return items