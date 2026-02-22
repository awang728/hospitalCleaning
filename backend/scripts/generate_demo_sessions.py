import random
import uuid
from datetime import datetime, timedelta
import numpy as np
import requests

BACKEND_URL = "http://127.0.0.1:8000/ingest/session"

ROOMS = ["ICU_12", "ICU_14", "ER_3", "OR_2"]
CLEANERS = ["alex", "navya", "ariuka", "arthur"]

# --- SURFACE PROFILES ---
# Each surface has its own grid size + high-touch definition
SURFACE_PROFILES = {
    # Wide rectangular surface
    "tray": {
        "grid_h": 20,
        "grid_w": 30,
        "high_touch": "tray_edges",
    },
    # Long thin surface
    "bedrail": {
        "grid_h": 10,
        "grid_w": 40,
        "high_touch": "bedrail_ends",
    },
    # Small localized surface
    "handle": {
        "grid_h": 12,
        "grid_w": 12,
        "high_touch": "handle_center",
    },
}

def make_high_touch_mask(surface_type: str, H: int, W: int) -> np.ndarray:
    m = np.zeros((H, W), dtype=int)
    mode = SURFACE_PROFILES[surface_type]["high_touch"]

    if mode == "tray_edges":
        # top strip + left strip
        m[0:3, :] = 1
        m[:, 0:3] = 1

    elif mode == "bedrail_ends":
        # ends of the rail (leftmost and rightmost columns)
        m[:, 0:5] = 1
        m[:, -5:] = 1

    elif mode == "handle_center":
        # central region
        r0, r1 = H//3, 2*H//3
        c0, c1 = W//3, 2*W//3
        m[r0:r1, c0:c1] = 1

    return m

def style_grid(style: str, ht_mask: np.ndarray) -> np.ndarray:
    """
    Returns coverage_count_grid (ints).
    Styles:
      - thorough
      - rushed_patchy
      - overwiper
      - misses_high_touch
    """
    H, W = ht_mask.shape
    g = np.zeros((H, W), dtype=int)

    if style == "thorough":
        cover = np.random.rand(H, W) < 0.92
        g[cover] = np.random.randint(1, 3, size=np.sum(cover))

    elif style == "rushed_patchy":
        # create a few blotchy clusters
        for _ in range(5):
            r = random.randint(0, max(0, H - 4))
            c = random.randint(0, max(0, W - 6))
            rh = min(3, H - r)
            cw = min(5, W - c)
            g[r:r+rh, c:c+cw] += np.random.randint(0, 2, size=(rh, cw))
        g[g > 0] += 1

    elif style == "overwiper":
        cover = np.random.rand(H, W) < 0.95
        g[cover] = np.random.randint(2, 7, size=np.sum(cover))

    elif style == "misses_high_touch":
        cover = np.random.rand(H, W) < 0.85
        g[cover] = np.random.randint(1, 3, size=np.sum(cover))
        g[ht_mask == 1] = 0

    return g

def post_session(room_id, surface_type, cleaner_id, style, start_time):
    prof = SURFACE_PROFILES[surface_type]
    H, W = prof["grid_h"], prof["grid_w"]

    ht = make_high_touch_mask(surface_type, H, W)
    grid = style_grid(style, ht)

    end_time = start_time + timedelta(seconds=random.randint(10, 180))

    payload = {
        "session_id": str(uuid.uuid4()),
        "surface_id": f"{surface_type.upper()}_{random.randint(1,5)}",
        "surface_type": surface_type,
        "room_id": room_id,
        "cleaner_id": cleaner_id,
        "start_time": start_time.isoformat() + "Z",
        "end_time": end_time.isoformat() + "Z",
        "grid_h": H,
        "grid_w": W,
        "coverage_count_grid": grid.tolist(),
        "high_touch_mask": ht.tolist(),
        "wipe_events": [],
        "camera_id": "SIMULATOR_1"
    }

    r = requests.post(BACKEND_URL, json=payload, timeout=10)
    if r.status_code != 200:
        print("POST failed:", r.status_code, r.text)
    return r.status_code

def main():
    random.seed(7)
    np.random.seed(7)

    now = datetime.utcnow()
    styles = ["thorough", "rushed_patchy", "overwiper", "misses_high_touch"]

    n = 120
    surface_types = list(SURFACE_PROFILES.keys())

    for i in range(n):
        room = random.choice(ROOMS)
        surf = random.choice(surface_types)
        cleaner = random.choice(CLEANERS)

        # create believable "trends"
        if room == "ICU_12":
            style = random.choices(styles, weights=[1, 4, 1, 2])[0]   # more rushed/missed
        elif surf == "bedrail":
            style = random.choices(styles, weights=[2, 1, 4, 1])[0]   # more overwiping
        elif surf == "handle":
            style = random.choices(styles, weights=[1, 2, 1, 4])[0]   # more missed high-touch
        else:
            style = random.choices(styles, weights=[3, 2, 2, 1])[0]

        start = now - timedelta(minutes=random.randint(0, 60*24*7))  # last 7 days
        code = post_session(room, surf, cleaner, style, start)

        if (i + 1) % 10 == 0:
            print(f"Inserted {i+1}/{n} (last status {code})")

    print("Done.")

if __name__ == "__main__":
    main()