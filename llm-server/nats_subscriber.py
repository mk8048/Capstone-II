import asyncio
import json
import nats


NATS_URL = "nats://localhost:4222"
SUBJECT = "llm.analysis"


async def main():
    nc = await nats.connect(NATS_URL)

    async def message_handler(msg):
        data = msg.data.decode("utf-8")
        parsed = json.loads(data)

        print("NATS 메시지 수신:")
        print(json.dumps(parsed, indent=2, ensure_ascii=False))

    await nc.subscribe(SUBJECT, cb=message_handler)

    print("구독 시작됨")
    print(f"subject: {SUBJECT}")

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())