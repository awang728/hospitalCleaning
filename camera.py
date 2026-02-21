import cv2
from ultralytics import YOLO
import mediapipe as mp
import numpy as np
import time

model = YOLO("yolov8n.pt")

mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles
mp_hands = mp.solutions.hands

threshold = 0.3

# --- Keep your helper functions as they were ---
def detect_tables(model, frame):
    results = model(frame, classes=[60], conf=0.15)
    boxes = []
    for box in results[0].boxes:
        boxes.append(tuple(map(int, box.xyxy[0])))
    return boxes

def create_table_mask(shape, table_boxes):
    mask = np.zeros(shape[:2], dtype=np.uint8)
    for (x1, y1, x2, y2) in table_boxes:
        cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)
    return mask

def create_missed_mask(heat_map, table_mask,threshold=threshold):
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

cap = cv2.VideoCapture(0)
table_boxes = []
preview_boxes = []
table_mask = None
heat_map = None
recording = False
finished = False
low_heatmap = None

with mp_hands.Hands(max_num_hands=2, model_complexity=0) as hands:
    while cap.isOpened():
        success, frame = cap.read()
        if not success: continue

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

        if not table_boxes:
            preview_boxes = []
            results = model(frame, classes=[60])
            preview_boxes = [tuple(map(int, box.xyxy[0])) for box in results[0].boxes]

        if not table_boxes:
            for (x1, y1, x2, y2) in preview_boxes:
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        
        if key == ord('s'):
            if not recording and not finished:
                if preview_boxes:
                    table_boxes = preview_boxes.copy()
                    table_mask = create_table_mask(frame.shape, table_boxes)
                    heat_map = np.zeros(frame.shape[:2], dtype=np.float32)
                    recording = True
                    start_time = time.time()
                    print("Session started")
            
            elif recording:
                recording = False
                finished = True
                print(f"Session finished. Time: {time.time() - start_time:.2f}s")
                total_area = np.count_nonzero(table_mask)
                missed_area = np.count_nonzero(create_missed_mask(heat_map, table_mask))

                if total_area > 0:
                    coverage = (1 - (missed_area / total_area)) * 100
                    print(f"Coverage: {coverage:.1f}%")

        if recording:
            frame = draw_heatmap(frame, heat_map)
        elif finished:
            frame = draw_low_heatmap(frame, heat_map, table_mask)

        for (x1, y1, x2, y2) in table_boxes:
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)

        cv2.imshow('Cleaning Tracker', cv2.flip(frame, 1))

        if key == 27:
            break

cap.release()
cv2.destroyAllWindows()