"""테스트용 NATS 발행 스크립트.

main-server `VisionPayload` schema와 `docs/nats-schema.md`를 따른다.
실행:
    python send_nats_test.py
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone

from nats.aio.client import Client as NATS


KST = timezone(timedelta(hours=9))


async def main() -> None:
    nc = NATS()
    await nc.connect("nats://127.0.0.1:4222")

    event_id = "evt_dashboard_test_001"
    payload = {
        "event_id": event_id,
        "camera_id": "cam01",
        "event_type": "person_detected",
        "source": "vision",
        "timestamp": datetime.now(KST).isoformat(),
        "data": {
            "object_count": 1,
            "max_confidence": 0.95,
            "image_key": f"events/{event_id}/thumb.jpg",
            "objects": [
                {
                    "class_name": "person",
                    "confidence": 0.95,
                    "bbox": [100, 200, 50, 100],
                    "track_id": None,
                },
            ],
        },
    }

    await nc.publish(
        "cs.vision.control.detected",
        json.dumps(payload).encode("utf-8"),
    )
    await nc.flush()
    await nc.close()
    print(f"published event_id={event_id}")


if __name__ == "__main__":
    asyncio.run(main())
