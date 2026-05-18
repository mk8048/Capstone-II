import asyncio
import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

from nats.aio.client import Client as NATS
from ultralytics import YOLO


NATS_URL = "nats://localhost:4222"
NATS_SUBJECT = "cs.vision.control.detected"

CAMERA_ID = "cam01"
MODEL_PATH = "yolov8n.pt"
IMAGE_SOURCE = "sample.jpg"
CONF_THRESHOLD = 0.5


def now_kst_iso() -> str:
    kst = timezone(timedelta(hours=9))
    return datetime.now(kst).isoformat(timespec="seconds")


def make_event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:8]}"


def xyxy_to_xywh(xyxy: list[float]) -> list[int]:
    x1, y1, x2, y2 = xyxy
    return [
        int(x1),
        int(y1),
        int(x2 - x1),
        int(y2 - y1),
    ]


def build_objects(result, model) -> list[dict]:
    objects = []

    for box in result.boxes:
        class_id = int(box.cls[0])
        class_name = model.names[class_id]
        confidence = float(box.conf[0])
        bbox = xyxy_to_xywh(box.xyxy[0].tolist())

        objects.append({
            "class_name": class_name,
            "confidence": round(confidence, 4),
            "bbox": bbox,
            "track_id": None
        })

    return objects


async def publish_message(message: dict) -> None:
    nc = NATS()
    await nc.connect(NATS_URL)

    payload = json.dumps(message, ensure_ascii=False).encode("utf-8")
    await nc.publish(NATS_SUBJECT, payload)

    await nc.drain()


async def main() -> None:
    image_path = Path(IMAGE_SOURCE)

    if not image_path.exists():
        raise FileNotFoundError(f"이미지 파일이 없습니다: {image_path.resolve()}")

    model = YOLO(MODEL_PATH)

    results = model.predict(
        source=str(image_path),
        conf=CONF_THRESHOLD,
        save=True
    )

    result = results[0]
    objects = build_objects(result, model)

    if not objects:
        print("탐지된 객체가 없습니다.")
        return

    event_id = make_event_id()
    max_confidence = max(obj["confidence"] for obj in objects)

    message = {
        "event_id": event_id,
        "camera_id": CAMERA_ID,
        "event_type": "person_detected",
        "source": "vision",
        "timestamp": now_kst_iso(),
        "data": {
            "object_count": len(objects),
            "max_confidence": max_confidence,
            "image_key": f"events/{event_id}/thumb.jpg",
            "objects": objects
        }
    }

    await publish_message(message)

    print("NATS 메시지 전송 완료")
    print(json.dumps(message, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
