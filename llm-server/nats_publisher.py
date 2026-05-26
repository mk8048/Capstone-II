"""JetStream publisher for cs.llm.control.update."""

import json


class LlmPublisher:
    def __init__(self, js, subject: str):
        self.js = js
        self.subject = subject

    async def publish(self, payload: dict) -> bool:
        try:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            await self.js.publish(self.subject, data)
            return True
        except Exception as e:
            print(f"[publisher] publish failed: {e}")
            return False
