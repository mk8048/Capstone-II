import asyncio
import json
from datetime import datetime

from llm_client import analyze_image
from nats_publisher import publish_message


IMAGE_PATH = "test.jpg"
MODEL_NAME = "ministral-3:latest"
EVENT_ID = "evt_0001"
CAMERA_ID = "cam01"


async def main():
    print("이미지 분석 시작")

    summary = analyze_image(IMAGE_PATH, MODEL_NAME)

    message = {
        "event_id": EVENT_ID,
        "camera_id": CAMERA_ID,
        "source": "llm",
        "timestamp": datetime.now().astimezone().isoformat(),
        "data": {
            "model_name": MODEL_NAME,
            "summary": summary
        }
    }

    print("NATS 전송 메시지:")
    print(json.dumps(message, indent=2, ensure_ascii=False))

    await publish_message(message)

    print("NATS publish 완료")


if __name__ == "__main__":
    asyncio.run(main())
