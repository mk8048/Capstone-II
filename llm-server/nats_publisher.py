import json
import nats


async def publish_message(data: dict):
    nc = await nats.connect("nats://localhost:4222")

    await nc.publish(
        "llm.analysis",
        json.dumps(data, ensure_ascii=False).encode("utf-8")
    )

    await nc.drain()