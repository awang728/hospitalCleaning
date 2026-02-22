import cv2
import numpy as np
import requests
import uuid
import json
import os
from datetime import datetime

# ==== CONFIG ====
GRID_H = 20
GRID_W = 30

BACKEND_URL = "http://127.0.0.1:8000/ingest/session"
SURFACE_TYPE = "tray"
SURFACE_ID = "TEST_SURFACE"
ROOM_ID = "ROOM_1"
CLEANER_ID = "test_user"
CAMERA_ID = "WEBCAM_1"

# Warped surface size (pixels)
WARP_W = 600
WARP_H = 400

# Motion detection tuning (UNCHANGED)
DIFF_THRESH = 25
CELL_MOTION_SUM_THRESH = 5000

# Cooldown (UNCHANGED)
COOLDOWN_FRAMES = 5

# Calibration save file (in same folder as this script)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CALIB_PATH = os.path.join(SCRIPT_DIR, "calibration_click.json")

cap = cv2.VideoCapture(0)

coverage_count_grid = np.zeros((GRID_H, GRID_W), dtype=int)
cooldown_grid = np.zeros((GRID_H, GRID_W), dtype=int)

session_active = False
start_time = None
current_session_id = None

prev_gray = None

# Homography (from click calibration)
H_mat = None

# Click calibration state
pick_mode = False
picked_pts = []  # list of (x,y) in camera frame


def make_high_touch_mask(grid_h: int, grid_w: int) -> np.ndarray:
    # Same MVP mask as before (top 3 rows + left 3 cols)
    mask = np.zeros((grid_h, grid_w), dtype=int)
    mask[0:3, :] = 1
    mask[:, 0:3] = 1
    return mask


HIGH_TOUCH_MASK = make_high_touch_mask(GRID_H, GRID_W)


def load_calibration():
    global H_mat
    if os.path.exists(CALIB_PATH):
        try:
            with open(CALIB_PATH, "r") as f:
                data = json.load(f)
            H = np.array(data["H"], dtype=np.float32)
            if H.shape != (3, 3):
                print("Calibration file exists but H is wrong shape. Ignoring.")
                return
            H_mat = H
            print(f"Loaded click calibration from {CALIB_PATH}")
        except Exception as e:
            print("Failed to load calibration:", e)


def save_calibration(H: np.ndarray, src_pts):
    data = {
        "H": H.tolist(),
        "warp_w": WARP_W,
        "warp_h": WARP_H,
        "src_pts": [[float(x), float(y)] for (x, y) in src_pts],
    }
    with open(CALIB_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved click calibration to {CALIB_PATH}")


def warp_with_H(frame, H: np.ndarray):
    return cv2.warpPerspective(frame, H, (WARP_W, WARP_H))


def compute_H_from_clicks(pts4):
    """
    pts4 must be in order: TL, TR, BR, BL in camera coordinates.
    """
    src = np.array(pts4, dtype="float32")
    dst = np.array([[0, 0], [WARP_W, 0], [WARP_W, WARP_H], [0, WARP_H]], dtype="float32")
    H = cv2.getPerspectiveTransform(src, dst)
    return H


def mouse_callback(event, x, y, flags, param):
    global picked_pts, pick_mode, H_mat
    if not pick_mode:
        return

    if event == cv2.EVENT_LBUTTONDOWN:
        picked_pts.append((x, y))
        print(f"Picked {len(picked_pts)}/4: ({x},{y})")

        # When we have all 4 points, compute H and save
        if len(picked_pts) == 4:
            H_mat = compute_H_from_clicks(picked_pts)
            save_calibration(H_mat, picked_pts)
            pick_mode = False
            print("Click calibration complete. You can now press S to start sessions.")


load_calibration()

print("Camera script running.")
print("Controls (click Camera window first):")
print("  K = pick 4 corners (TL, TR, BR, BL) on Camera window")
print("  S = start session")
print("  E = end session (POST to backend)")
print("  Q = quit")

# Create windows early so we can attach mouse callback
cv2.namedWindow("Camera")
cv2.setMouseCallback("Camera", mouse_callback)

while True:
    ret, frame = cap.read()
    if not ret:
        print("Failed to read from camera.")
        break

    # Instructions only on CAMERA window
    cv2.putText(
        frame,
        "K=pick corners | S=start | E=end | Q=quit (click here)",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 0, 255),
        2
    )

    # If in pick mode, show progress + draw picked points
    if pick_mode:
        cv2.putText(
            frame,
            f"CORNER PICK MODE: click TL,TR,BR,BL ({len(picked_pts)}/4)",
            (10, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2
        )
        for i, (px, py) in enumerate(picked_pts):
            cv2.circle(frame, (int(px), int(py)), 6, (0, 0, 255), -1)
            cv2.putText(
                frame,
                str(i + 1),
                (int(px) + 8, int(py) - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 255),
                2
            )

    # Warp if calibrated
    warped = None
    if H_mat is not None:
        warped = warp_with_H(frame, H_mat)

    if warped is not None:
        gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        if session_active:
            cooldown_grid = np.maximum(cooldown_grid - 1, 0)

        if prev_gray is not None and session_active:
            diff = cv2.absdiff(gray, prev_gray)
            _, thresh = cv2.threshold(diff, DIFF_THRESH, 255, cv2.THRESH_BINARY)

            h, w = thresh.shape
            cell_h = h // GRID_H
            cell_w = w // GRID_W

            for i in range(GRID_H):
                for j in range(GRID_W):
                    if cooldown_grid[i, j] > 0:
                        continue
                    cell = thresh[i * cell_h:(i + 1) * cell_h, j * cell_w:(j + 1) * cell_w]
                    if np.sum(cell) > CELL_MOTION_SUM_THRESH:
                        coverage_count_grid[i, j] += 1
                        cooldown_grid[i, j] = COOLDOWN_FRAMES

        prev_gray = gray.copy()

        # Warped window: no red instructions
        cv2.imshow("Warped Surface", warped)
    else:
        prev_gray = None

    cv2.imshow("Camera", frame)

    key = cv2.waitKey(1) & 0xFF

    # Enter pick mode
    if key == ord('k'):
        pick_mode = True
        picked_pts = []
        print("\nPick mode ON. Click corners in order: TL, TR, BR, BL.")

    # Start session
    if key == ord('s') and not session_active:
        if H_mat is None:
            print("Cannot start session: not calibrated yet. Press K and click 4 corners first.")
            continue

        session_active = True
        start_time = datetime.utcnow()
        current_session_id = str(uuid.uuid4())

        coverage_count_grid = np.zeros((GRID_H, GRID_W), dtype=int)
        cooldown_grid = np.zeros((GRID_H, GRID_W), dtype=int)
        prev_gray = None

        print("\nSession Started")
        print("SESSION_ID:", current_session_id)
        print("Start time (UTC):", start_time.isoformat() + "Z")

    # End session
    if key == ord('e') and session_active:
        end_time = datetime.utcnow()
        session_active = False

        print("Session Ended")
        print("End time (UTC):", end_time.isoformat() + "Z")

        payload = {
            "session_id": current_session_id,
            "surface_id": SURFACE_ID,
            "surface_type": SURFACE_TYPE,
            "room_id": ROOM_ID,
            "cleaner_id": CLEANER_ID,
            "start_time": start_time.isoformat() + "Z",
            "end_time": end_time.isoformat() + "Z",
            "grid_h": GRID_H,
            "grid_w": GRID_W,
            "coverage_count_grid": coverage_count_grid.tolist(),
            "high_touch_mask": HIGH_TOUCH_MASK.tolist(),
            "wipe_events": [],
            "camera_id": CAMERA_ID
        }

        try:
            r = requests.post(BACKEND_URL, json=payload, timeout=10)
            print("Backend Response:", r.status_code)
            if r.status_code != 200:
                print("Backend body:", r.text)
        except Exception as ex:
            print("Failed to POST to backend:", ex)

        print("SESSION_ID (saved):", current_session_id)

    if key == ord('q'):
        print("Quitting.")
        break

cap.release()
cv2.destroyAllWindows()