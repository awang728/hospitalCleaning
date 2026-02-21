import cv2
from ultralytics import YOLO
import mediapipe as mp
import numpy as np

model = YOLO("yolov8n.pt")

mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles
mp_hands = mp.solutions.hands

def detect_tables(model, frame):
    results = model(frame, classes=[60])
    boxes = []

    for box in results[0].boxes:
        boxes.append(tuple(map(int, box.xyxy[0])))
    return boxes


def create_table_mask(shape, table_boxes):
    mask = np.zeros(shape[:2], dtype=np.uint8)

    for (x1, y1, x2, y2) in table_boxes:
        cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)
    return mask


def get_palm(hand_landmarks, frame_shape):
    h, w = frame_shape[:2]

    x0 = int(hand_landmarks.landmark[0].x * w)
    y0 = int(hand_landmarks.landmark[0].y * h)

    x9 = int(hand_landmarks.landmark[9].x * w)
    y9 = int(hand_landmarks.landmark[9].y * h)

    return ((x0 + x9) // 2, (y0 + y9) // 2)


def draw_heatmap(frame, heat_map):
    overlay = np.zeros_like(frame)
    overlay[:, :, 2] = (heat_map * 255).astype(np.uint8)
    return cv2.addWeighted(frame, 1.0, overlay, 1.0, 0)


def update_heatmap(heat_map, table_mask, palm, radius=40, increment=0.02):
    circle_mask = np.zeros_like(table_mask)
    cv2.circle(circle_mask, palm, radius, 255, -1)

    intersection = cv2.bitwise_and(table_mask, circle_mask)
    heat_map[intersection == 255] += increment

    np.clip(heat_map, 0, 1, out=heat_map)


cap = cv2.VideoCapture(0)
table_boxes = []
table_mask = None
heat_map = None
recording = False


with mp_hands.Hands(max_num_hands=1, model_complexity=0) as hands:
  
    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            continue

        key = cv2.waitKey(5) & 0xFF

        if not table_boxes:
            results = model(frame, classes=[60])
            for box in results[0].boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)


        if not table_boxes and key == ord('s'): #'s' key to start session
            table_boxes = detect_tables(model, frame)
            table_mask = create_table_mask(frame.shape, table_boxes)
            recording = True

        for (x1, y1, x2, y2) in table_boxes:
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

        if heat_map is None:
            heat_map = np.zeros(frame.shape[:2], dtype=np.float32)

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
                cv2.circle(frame, palm, 40, (0, 255, 255), 2)

                if table_mask is not None:
                    update_heatmap(heat_map, table_mask, palm)

        frame = draw_heatmap(frame, heat_map)

        cv2.imshow('MediaPipe Hands', cv2.flip(frame, 1))

        if key == 27:
            break

cap.release()
cv2.destroyAllWindows()