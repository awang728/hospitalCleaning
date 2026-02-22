import cv2
import mediapipe as mp
import numpy as np
import threading
import time
import uuid
import requests
from datetime import datetime
from ultralytics import YOLO
import os
from dotenv import load_dotenv

load_dotenv()

INGEST_API_KEY = os.getenv("INGEST_API_KEY")
BACKEND_URL = "http://127.0.0.1:8000/ingest/session"

ROOM_ID = "ICU_12"
SURFACE_TYPE = "tray"
SURFACE_ID = "TRAY_1"
CLEANER_ID = "arthur"
CAMERA_ID = "WEBCAM_1"

SURFACE_PROFILES = {
    "tray":    {"grid_h": 20, "grid_w": 30},
    "bedrail": {"grid_h": 10, "grid_w": 40},
    "handle":  {"grid_h": 12, "grid_w": 12},
}

THRESHOLD = 0.3

_lock = threading.Lock()
_state = {
    "coverage_percent": 0.0,
    "high_touch_done": False,
    "recording": False,
    "finished": False,
    "heat_map": None,
    "table_mask": None,
    "table_boxes": [],
    "session_id": None,
    "start_time_utc": None,
    "start_time": None,
}

model = YOLO("yolov8n.pt")
model.overrides["verbose"] = False

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

# Shared preview boxes so /camera/start can use the latest detected boxes
_preview_boxes = []


def get_state():
    with _lock:
        return {k: v for k, v in _state.items() if k not in ("heat_map", "table_mask")}


def start_session(frame_shape, preview_boxes):
    with _lock:
        if _state["recording"] or not preview_boxes:
            return False
        mask = np.zeros(frame_shape[:2], dtype=np.uint8)
        for (x1, y1, x2, y2) in preview_boxes:
            cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)
        _state["table_boxes"] = list(preview_boxes)
        _state["table_mask"] = mask
        _state["heat_map"] = np.zeros(frame_shape[:2], dtype=np.float32)
        _state["recording"] = True
        _state["finished"] = False
        _state["session_id"] = str(uuid.uuid4())
        _state["start_time_utc"] = datetime.utcnow()
        _state["start_time"] = time.time()
        _state["coverage_percent"] = 0.0
        _state["high_touch_done"] = False
        print("Session started:", _state["session_id"])
        return True


def stop_session():
    with _lock:
        if not _state["recording"]:
            return False
        _state["recording"] = False
        _state["finished"] = True
        end_time_utc = datetime.utcnow()
        elapsed = time.time() - _state["start_time"]
        print(f"Session finished. Duration: {elapsed:.1f}s")

        heat_map = _state["heat_map"]
        table_mask = _state["table_mask"]
        table_boxes = _state["table_boxes"]

        prof = SURFACE_PROFILES.get(SURFACE_TYPE, SURFACE_PROFILES["tray"])
        gh, gw = prof["grid_h"], prof["grid_w"]

        chosen = max(table_boxes, key=lambda b: (b[2]-b[0])*(b[3]-b[1]))
        grid = _heatmap_to_grid(heat_map, chosen, gh, gw)
        high_touch = _make_high_touch_mask(SURFACE_TYPE, gh, gw)

        payload = {
            "session_id": _state["session_id"],
            "surface_id": SURFACE_ID,
            "surface_type": SURFACE_TYPE,
            "room_id": ROOM_ID,
            "cleaner_id": CLEANER_ID,
            "start_time": _state["start_time_utc"].isoformat() + "Z",
            "end_time": end_time_utc.isoformat() + "Z",
            "grid_h": gh,
            "grid_w": gw,
            "coverage_count_grid": grid.tolist(),
            "high_touch_mask": high_touch.tolist(),
            "wipe_events": [],
            "camera_id": CAMERA_ID,
        }

    threading.Thread(target=_post_session, args=(payload,), daemon=True).start()

    # Reset back to clean slate so user can immediately start another session
    with _lock:
        _state["finished"] = False
        _state["recording"] = False
        _state["table_boxes"] = []
        _state["table_mask"] = None
        _state["heat_map"] = None
        _state["coverage_percent"] = 0.0
        _state["high_touch_done"] = False
        _state["session_id"] = None
        _state["start_time_utc"] = None
        _state["start_time"] = None

    return True


def _post_session(payload):
    try:
        headers = {"X-API-Key": INGEST_API_KEY} if INGEST_API_KEY else {}
        r = requests.post(BACKEND_URL, json=payload, headers=headers, timeout=10)
        print("POST /ingest/session ->", r.status_code)
        if r.status_code != 200:
            print("Backend error:", r.text)
    except Exception as e:
        print("Failed to post session:", e)


def _detect_surface(frame):
    """
    Multi-stage surface detection:
    1. YOLO table class (class 60)
    2. Any large YOLO-detected object (>8% of frame)
    3. OpenCV contour-based flat region detection — finds large rectangular
       regions regardless of what they are, great for trays/beds/surfaces
    4. Near-full-frame fallback — very small margins so almost the whole
       frame is used as the cleaning area
    """
    h, w = frame.shape[:2]

    # Stage 1: YOLO table
    res = model(frame, classes=[60], conf=0.08, verbose=False)
    boxes = [tuple(map(int, b.xyxy[0])) for b in res[0].boxes]
    if boxes:
        return boxes

    # Stage 2: any large YOLO object
    res2 = model(frame, conf=0.08, verbose=False)
    min_area = h * w * 0.08
    large_boxes = []
    for b in res2[0].boxes:
        x1, y1, x2, y2 = map(int, b.xyxy[0])
        if (x2 - x1) * (y2 - y1) >= min_area:
            large_boxes.append((x1, y1, x2, y2))
    if large_boxes:
        return large_boxes

    # Stage 3: OpenCV contour detection — finds flat/rectangular regions
    # Works well for trays, tables, beds, any large flat surface
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (11, 11), 0)
    edges = cv2.Canny(blurred, 20, 80)
    dilated = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=2)
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_contour_area = h * w * 0.08
    contour_boxes = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area >= min_contour_area:
            x, y, cw, ch = cv2.boundingRect(cnt)
            # Only keep roughly rectangular regions (not thin lines)
            aspect = cw / ch if ch > 0 else 0
            if 0.3 < aspect < 6.0:
                contour_boxes.append((x, y, x + cw, y + ch))
    if contour_boxes:
        # Return the largest one
        contour_boxes.sort(key=lambda b: (b[2]-b[0])*(b[3]-b[1]), reverse=True)
        return [contour_boxes[0]]

    # Stage 4: near-full-frame fallback — very small margins
    margin_x = w // 10
    margin_y = h // 10
    return [(margin_x, margin_y, w - margin_x, h - margin_y)]


def _get_palm(lm, shape):
    h, w = shape[:2]
    x0 = int(lm.landmark[0].x * w); y0 = int(lm.landmark[0].y * h)
    x9 = int(lm.landmark[9].x * w); y9 = int(lm.landmark[9].y * h)
    return ((x0+x9)//2, (y0+y9)//2)


def _get_radius(lm, shape, scale=0.75):
    h, w = shape[:2]
    x0 = int(lm.landmark[0].x * w); y0 = int(lm.landmark[0].y * h)
    x9 = int(lm.landmark[9].x * w); y9 = int(lm.landmark[9].y * h)
    return int(((x0-x9)**2+(y0-y9)**2)**0.5 * scale)


def _update_heatmap(heat_map, table_mask, palm, radius):
    circle = np.zeros_like(table_mask)
    cv2.circle(circle, palm, radius, 255, -1)
    inter = cv2.bitwise_and(table_mask, circle)
    heat_map[inter == 255] += 0.02
    np.clip(heat_map, 0, 1, out=heat_map)


def _compute_coverage(heat_map, table_mask):
    total = np.count_nonzero(table_mask)
    if total == 0:
        return 0.0
    missed = np.count_nonzero((heat_map < THRESHOLD) & (table_mask == 255))
    return (1 - missed / total) * 100


def _high_touch_done(heat_map, table_mask):
    if heat_map is None or table_mask is None:
        return False
    h, w = heat_map.shape
    margin = max(1, min(h, w) // 8)
    edge = table_mask.copy()
    interior = np.zeros_like(edge)
    interior[margin:-margin, margin:-margin] = table_mask[margin:-margin, margin:-margin]
    edge_mask = cv2.subtract(edge, interior)
    total = np.count_nonzero(edge_mask)
    if total == 0:
        return False
    covered = np.count_nonzero((heat_map >= THRESHOLD) & (edge_mask == 255))
    return (covered / total) >= 0.6


def _make_high_touch_mask(surface_type, H, W):
    m = np.zeros((H, W), dtype=int)
    if surface_type == "tray":
        m[0:3, :] = 1
        m[:, 0:3] = 1
    elif surface_type == "bedrail":
        m[:, 0:5] = 1
        m[:, -5:] = 1
    else:
        r0, r1 = H//3, 2*H//3
        c0, c1 = W//3, 2*W//3
        m[r0:r1, c0:c1] = 1
    return m


def _heatmap_to_grid(heat_map, table_box, grid_h, grid_w):
    x1, y1, x2, y2 = table_box
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(heat_map.shape[1], x2), min(heat_map.shape[0], y2)
    roi = heat_map[y1:y2, x1:x2]
    if roi.size == 0:
        return np.zeros((grid_h, grid_w), dtype=int)
    h, w = roi.shape
    cell_h = max(1, h // grid_h)
    cell_w = max(1, w // grid_w)
    grid = np.zeros((grid_h, grid_w), dtype=int)
    for r in range(grid_h):
        for c in range(grid_w):
            ys, xs = r*cell_h, c*cell_w
            ye = (r+1)*cell_h if r < grid_h-1 else h
            xe = (c+1)*cell_w if c < grid_w-1 else w
            cell = roi[ys:ye, xs:xe]
            mean_heat = float(np.mean(cell)) if cell.size else 0.0
            grid[r, c] = int(round(mean_heat * 10))
    return grid


def generate_frames():
    global _preview_boxes
    cap = cv2.VideoCapture(0)

    with mp_hands.Hands(max_num_hands=2, model_complexity=0) as hands:
        while True:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame.flags.writeable = False
            res = hands.process(rgb)
            frame.flags.writeable = True

            with _lock:
                recording = _state["recording"]
                finished = _state["finished"]
                table_boxes = list(_state["table_boxes"])
                heat_map = _state["heat_map"]
                table_mask = _state["table_mask"]

            # Always detect surface when not recording (keeps preview_boxes fresh)
            if not recording and not table_boxes:
                detected = _detect_surface(frame)
                _preview_boxes = detected
                for (x1, y1, x2, y2) in detected:
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, "Surface ready — press Start Session", (10, 35),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 0), 2)

            elif table_boxes:
                for (x1, y1, x2, y2) in table_boxes:
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 180, 0), 2)

            # Process hands
            if res.multi_hand_landmarks:
                for lm in res.multi_hand_landmarks:
                    mp_drawing.draw_landmarks(frame, lm, mp_hands.HAND_CONNECTIONS,
                        mp_drawing_styles.get_default_hand_landmarks_style(),
                        mp_drawing_styles.get_default_hand_connections_style())
                    palm = _get_palm(lm, frame.shape)
                    radius = _get_radius(lm, frame.shape)
                    cv2.circle(frame, palm, radius, (0, 255, 255), 2)
                    if recording and table_mask is not None:
                        with _lock:
                            _update_heatmap(_state["heat_map"], _state["table_mask"], palm, radius)

            # Heatmap overlays
            with _lock:
                heat_map = _state["heat_map"]
                table_mask = _state["table_mask"]

            if recording and heat_map is not None:
                overlay = np.zeros_like(frame)
                overlay[:, :, 2] = (heat_map * 255).astype(np.uint8)
                frame = cv2.addWeighted(frame, 1.0, overlay, 1.0, 0)
                cov = _compute_coverage(heat_map, table_mask)
                ht = _high_touch_done(heat_map, table_mask)
                with _lock:
                    _state["coverage_percent"] = round(cov, 1)
                    _state["high_touch_done"] = ht
                cv2.putText(frame, f"RECORDING  Coverage: {cov:.1f}%", (10, 35),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 80, 255), 2)

            elif finished and heat_map is not None and table_mask is not None:
                overlay = np.zeros_like(frame)
                low_clean = (heat_map < THRESHOLD) & (table_mask == 255)
                overlay[low_clean, 1] = 255
                frame = cv2.addWeighted(frame, 1.0, overlay, 0.6, 0)
                cv2.putText(frame, "Done — green = missed zones", (10, 35),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 0), 2)

            _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                   + buf.tobytes() + b'\r\n')

    cap.release()