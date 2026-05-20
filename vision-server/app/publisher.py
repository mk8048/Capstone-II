"""JetStream publisher. Persistent connection, ack-confirmed publish."""

import json

import nats


class NatsPublisher:
    def __init__(self, nats_url: str, subject: str):
        self.nats_url = nats_url
        self.subject = subject
        self.nc = None
        self.js = None

    async def connect(self) -> None:
        self.nc = await nats.connect(self.nats_url)
        self.js = self.nc.jetstream()

    async def publish(self, payload: dict) -> bool:
        try:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            await self.js.publish(self.subject, data)
            return True
        except Exception as e:
            print(f"[publisher] publish failed: {e}")
            return False

    async def close(self) -> None:
        if self.nc is not None:
            await self.nc.drain()
