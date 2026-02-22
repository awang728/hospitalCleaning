import os
import warnings
from dotenv import load_dotenv

# =========================
# SILENCE / DEBUG TOGGLE
# =========================
DEBUG = False

# Silence TensorFlow/MediaPipe/absl noise (safe; doesn't change behavior)
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["GLOG_minloglevel"] = "3"
os.environ["ABSL_MIN_LOG_LEVEL"] = "3"

# Hide protobuf/mediapipe deprecation warnings
if not DEBUG:
    warnings.filterwarnings("ignore", category=UserWarning)
    warnings.filterwarnings("ignore", message="SymbolDatabase.GetPrototype")

import cv2
from ultralytics import YOLO
import mediapipe as mp
import numpy as np
import time
import uuid
import requests
from datetime import datetime

load_dotenv()

INGEST_API_KEY = os.getenv("INGEST_API_KEY")

# =========================
# CONFIG (match your backend)
# =========================
BACKEND_URL = "http://127.0.0.1:8000/ingest/session"

ROOM_ID = "ICU_12"
SURFACE_TYPE = "tray"        # tray / bedrail / handle
SURFACE_ID = "TRAY_1"
CLEANER_ID = "arthur"
CAMERA_ID = "WEBCAM_1"

# Choose grid size per surface profile (IMPORTANT: must match high_touch_mask shape)
SURFACE_PROFILES = {
    "tray":    {"grid_h": 20, "grid_w": 30},
    "bedrail": {"grid_h": 10, "grid_w": 40},
    "handle":  {"grid_h": 12, "grid_w": 12},
}

threshold = 0.3  # Arthur's low-coverage threshold

# =========================
# Load Models (YOLO verbosity controlled)
# =========================
model = YOLO("yolov8n.pt")
model.overrides["verbose"] = DEBUG

mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles
mp_hands = mp.solutions.hands

# =========================
# Helpers (Arthur originals)
# =========================
def detect_tables(model, frame):
    results = model(frame, classes=[60], conf=0.15, verbose=DEBUG)
    boxes = []
    for box in results[0].boxes:
        boxes.append(tuple(map(int, box.xyxy[0])))
    return boxes

def create_table_mask(shape, table_boxes):
    mask = np.zeros(shape[:2], dtype=np.uint8)
    for (x1, y1, x2, y2) in table_boxes:
        cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)
    return mask

def create_missed_mask(heat_map, table_mask, threshold=threshold):
    missed = (heat_map < threshold) & (table_mask == 255)
    missed_mask = np.zeros_like(table_mask)
    missed_mask[missed] = 255
    return missed_mask

def get_palm(hand_landmarks, frame_shape):
    h, w = frame_shape[:2]
    x0 = int(hand_landmarks.landmark[0].x * w)
    y0 = int(hand_landmarks.landmark[0].y * h)
    x9 = int(hand_landmarks.landmark[9].x * w)
    y9 = int(hand_landmarks.landmark[9].y * h)
    return ((x0 + x9) // 2, (y0 + y9) // 2)

def get_palm_radius(hand_landmarks, frame_shape, scale=0.75):
    h, w = frame_shape[:2]
    x0 = int(hand_landmarks.landmark[0].x * w)
    y0 = int(hand_landmarks.landmark[0].y * h)
    x9 = int(hand_landmarks.landmark[9].x * w)
    y9 = int(hand_landmarks.landmark[9].y * h)
    distance = ((x0 - x9)**2 + (y0 - y9)**2)**0.5
    return int(distance * scale)

def draw_heatmap(frame, heat_map):
    overlay = np.zeros_like(frame)
    overlay[:, :, 2] = (heat_map * 255).astype(np.uint8)
    return cv2.addWeighted(frame, 1.0, overlay, 1.0, 0)

def draw_low_heatmap(frame, heat_map, table_mask, threshold=threshold):
    overlay = np.zeros_like(frame)
    low_clean = (heat_map < threshold) & (table_mask == 255)
    overlay[low_clean, 1] = 255
    return cv2.addWeighted(frame, 1.0, overlay, 0.6, 0)

def update_heatmap(heat_map, table_mask, palm, radius, increment=0.02):
    circle_mask = np.zeros_like(table_mask)
    cv2.circle(circle_mask, palm, radius, 255, -1)
    intersection = cv2.bitwise_and(table_mask, circle_mask)
    heat_map[intersection == 255] += increment
    np.clip(heat_map, 0, 1, out=heat_map)

# =========================
# NEW: convert pixel heat_map to backend grid
# =========================
def make_high_touch_mask(surface_type: str, H: int, W: int) -> np.ndarray:
    m = np.zeros((H, W), dtype=int)
    if surface_type == "tray":
        m[0:3, :] = 1
        m[:, 0:3] = 1
    elif surface_type == "bedrail":
        m[:, 0:5] = 1
        m[:, -5:] = 1
    else:  # handle
        r0, r1 = H // 3, 2 * H // 3
        c0, c1 = W // 3, 2 * W // 3
        m[r0:r1, c0:c1] = 1
    return m

def heatmap_to_grid(heat_map: np.ndarray, table_box, grid_h: int, grid_w: int) -> np.ndarray:
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
            ys = r * cell_h
            xs = c * cell_w
            ye = (r + 1) * cell_h if r < grid_h - 1 else h
            xe = (c + 1) * cell_w if c < grid_w - 1 else w
            cell = roi[ys:ye, xs:xe]
            mean_heat = float(np.mean(cell)) if cell.size else 0.0
            grid[r, c] = int(round(mean_heat * 10))
    return grid

# =========================
# Main loop
# =========================
cap = cv2.VideoCapture(0)

table_boxes = []
preview_boxes = []
table_mask = None
heat_map = None
recording = False
finished = False

session_id = None
start_time_utc = None

with mp_hands.Hands(max_num_hands=2, model_complexity=0) as hands:
    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            continue

        key = cv2.waitKey(5) & 0xFF

        # Convert to RGB for MediaPipe
        frame.flags.writeable = False
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb)
        frame.flags.writeable = True

        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                mp_drawing.draw_landmarks(
                    frame,
                    hand_landmarks,
                    mp_hands.HAND_CONNECTIONS,
                    mp_drawing_styles.get_default_hand_landmarks_style(),
                    mp_drawing_styles.get_default_hand_connections_style()
                )
                palm = get_palm(hand_landmarks, frame.shape)
                radius = get_palm_radius(hand_landmarks, frame.shape)
                cv2.circle(frame, palm, radius, (0, 255, 255), 2)

                if recording and table_mask is not None:
                    update_heatmap(heat_map, table_mask, palm, radius=radius)

        # Detect table boxes (preview mode)
        if not table_boxes:
            results_yolo = model(frame, classes=[60], verbose=DEBUG)
            preview_boxes = [tuple(map(int, box.xyxy[0])) for box in results_yolo[0].boxes]

        # Draw preview boxes
        if not table_boxes:
            for (x1, y1, x2, y2) in preview_boxes:
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

        # Start/Stop with 's'
        if key == ord('s'):
            if not recording and not finished:
                if preview_boxes:
                    table_boxes = preview_boxes.copy()
                    table_mask = create_table_mask(frame.shape, table_boxes)
                    heat_map = np.zeros(frame.shape[:2], dtype=np.float32)
                    recording = True
                    finished = False

                    session_id = str(uuid.uuid4())
                    start_time_utc = datetime.utcnow()

                    start_time = time.time()
                    print("Session started")
                    print("SESSION_ID:", session_id)

            elif recording:
                recording = False
                finished = True
                end_time_utc = datetime.utcnow()

                print(f"Session finished. Time: {time.time() - start_time:.2f}s")

                total_area = np.count_nonzero(table_mask)
                missed_area = np.count_nonzero(create_missed_mask(heat_map, table_mask))
                if total_area > 0:
                    coverage = (1 - (missed_area / total_area)) * 100
                    print(f"Coverage: {coverage:.1f}%")

                prof = SURFACE_PROFILES.get(SURFACE_TYPE, SURFACE_PROFILES["tray"])
                gh, gw = prof["grid_h"], prof["grid_w"]

                chosen = max(table_boxes, key=lambda b: (b[2]-b[0])*(b[3]-b[1]))
                grid = heatmap_to_grid(heat_map, chosen, gh, gw)
                high_touch = make_high_touch_mask(SURFACE_TYPE, gh, gw)

                payload = {
                    "session_id": session_id,
                    "surface_id": SURFACE_ID,
                    "surface_type": SURFACE_TYPE,
                    "room_id": ROOM_ID,
                    "cleaner_id": CLEANER_ID,
                    "start_time": start_time_utc.isoformat() + "Z",
                    "end_time": end_time_utc.isoformat() + "Z",
                    "grid_h": gh,
                    "grid_w": gw,
                    "coverage_count_grid": grid.tolist(),
                    "high_touch_mask": high_touch.tolist(),
                    "wipe_events": [],
                    "camera_id": CAMERA_ID,
                }

                try:
                    print("SESSION_ID:", session_id)
                    headers = {"X-API-Key": INGEST_API_KEY} if INGEST_API_KEY else {}

                    r = requests.post(BACKEND_URL, json=payload, headers=headers, timeout=10)
                    print("POST /ingest/session ->", r.status_code)
                    print("SUMMARY URL:", f"http://127.0.0.1:8000/sessions/{session_id}/summary")
                    if r.status_code != 200:
                        print("Backend body:", r.text)
                except Exception as ex:
                    print("Failed to post to backend:", ex)

        if recording:
            frame = draw_heatmap(frame, heat_map)
        elif finished and heat_map is not None and table_mask is not None:
            frame = draw_low_heatmap(frame, heat_map, table_mask)

        for (x1, y1, x2, y2) in table_boxes:
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)

        cv2.imshow('Cleaning Tracker', cv2.flip(frame, 1))

        if key == 27:
            break

cap.release()
cv2.destroyAllWindows()