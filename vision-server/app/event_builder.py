"""NATS payload assembly per docs/nats-schema.md."""

import uuid
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def make_event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:8]}"


def now_kst_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def build_event(
    event_id: str,
    camera_id: str,
    image_key: str,
    objects: list[dict],
) -> dict:
    return {
        "event_id": event_id,
        "camera_id": camera_id,
        "event_type": "person_detected",
        "source": "vision",
        "timestamp": now_kst_iso(),
        "data": {
            "object_count": len(objects),
            "max_confidence": max(o["confidence"] for o in objects),
            "image_key": image_key,
            "objects": objects,
        },
    }
