import cv2
from ultralytics import YOLO
import mediapipe as mp
import numpy as np

mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles
mp_hands = mp.solutions.hands

model = YOLO("yolov8n.pt")

cap = cv2.VideoCapture(0)
table_boxes = []
heat_map = None

with mp_hands.Hands(
    model_complexity=0,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5) as hands:
  
  while cap.isOpened():
    success, image = cap.read()
    if not success:
      print("Ignoring empty camera frame.")
      continue

    if heat_map is None:
      heat_map = np.zeros(image.shape[:2], dtype=np.float32)

    if not table_boxes:
      results = model(image, classes=[60])
      for box in results[0].boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        table_boxes.append((x1, y1, x2, y2))

    for (x1, y1, x2, y2) in table_boxes:
      cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)

    image.flags.writeable = False
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    hand_results = hands.process(image)

    image.flags.writeable = True
    image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

    if hand_results.multi_hand_landmarks:
      for hand_landmarks in hand_results.multi_hand_landmarks:
        mp_drawing.draw_landmarks(
            image,
            hand_landmarks,
            mp_hands.HAND_CONNECTIONS,
            mp_drawing_styles.get_default_hand_landmarks_style(),
            mp_drawing_styles.get_default_hand_connections_style())

        h, w, _ = image.shape
        x0 = int(hand_landmarks.landmark[0].x * w)
        y0 = int(hand_landmarks.landmark[0].y * h)
        x9 = int(hand_landmarks.landmark[9].x * w)
        y9 = int(hand_landmarks.landmark[9].y * h)
        palm_center = ((x0 + x9) // 2, (y0 + y9) // 2)
        print(f"Palm: {palm_center}")
        cv2.circle(image, palm_center, 40, (0, 255, 255), 2)

        for (x1, y1, x2, y2) in table_boxes:
          box_mask = np.zeros(image.shape[:2], dtype=np.uint8)
          cv2.rectangle(box_mask, (x1, y1), (x2, y2), 255, -1)
          circle_mask = np.zeros(image.shape[:2], dtype=np.uint8)
          cv2.circle(circle_mask, palm_center, 40, 255, -1)
          intersection = cv2.bitwise_and(box_mask, circle_mask)
          heat_map[intersection == 255] += 0.02
          heat_map = np.clip(heat_map, 0, 1)

    red_overlay = np.zeros_like(image)
    red_overlay[:, :, 2] = (heat_map * 255).astype(np.uint8)
    image = cv2.addWeighted(image, 1.0, red_overlay, 1.0, 0)

    cv2.imshow('MediaPipe Hands', cv2.flip(image, 1))
    if cv2.waitKey(5) & 0xFF == 27:
      break

cap.release()
cv2.destroyAllWindows()