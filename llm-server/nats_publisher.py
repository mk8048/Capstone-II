import json
import nats


NATS_URL = "nats://localhost:4222"
SUBJECT = "llm.analysis"


async def publish_message(message):
    nc = await nats.connect(NATS_URL)

    payload = json.dumps(message, ensure_ascii=False).encode("utf-8")

    await nc.publish(SUBJECT, payload)
    await nc.drain()
