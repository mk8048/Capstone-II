import asyncio
import json
from datetime import datetime

from llm_client import analyze_image
from nats_publisher import publish_message

IMAGE_PATH = "test.jpg"


async def main():
    print("이미지 분석 시작")

    result_text = analyze_image(IMAGE_PATH)

    print("LLM 분석 결과:")
    print(result_text)

    message = {
        "type": "llm_analysis",
        "timestamp": datetime.now().isoformat(),
        "image_path": IMAGE_PATH,
        "result": result_text
    }

    await publish_message(message)

    print("NATS publish 완료")


if __name__ == "__main__":
    asyncio.run(main())