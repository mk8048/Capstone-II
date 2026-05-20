"""YOLO detector with person-only filter."""

from ultralytics import YOLO

PERSON_CLASS_NAME = "person"


class PersonDetector:
    def __init__(self, model_path: str, device: str, conf_threshold: float):
        self.model = YOLO(model_path)
        self.device = device
        self.conf_threshold = conf_threshold

    def detect_persons(self, frame) -> list[dict]:
        results = self.model.predict(
            source=frame,
            conf=self.conf_threshold,
            device=self.device,
            verbose=False,
        )
        result = results[0]
        persons: list[dict] = []
        for box in result.boxes:
            class_id = int(box.cls[0])
            class_name = self.model.names[class_id]
            if class_name != PERSON_CLASS_NAME:
                continue
            confidence = float(box.conf[0])
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            persons.append(
                {
                    "class_name": class_name,
                    "confidence": round(confidence, 4),
                    "bbox": [int(x1), int(y1), int(x2 - x1), int(y2 - y1)],
                    "track_id": None,
                }
            )
        return persons
