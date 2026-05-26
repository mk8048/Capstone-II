import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import llm_client
import nats_subscriber


class FakeMsg:
    def __init__(self, payload):
        self.data = json.dumps(payload).encode("utf-8")
        self.ack = AsyncMock()


class FakeFetcher:
    def __init__(self, image_bytes=b"image"):
        self.image_bytes = image_bytes
        self.keys = []

    def fetch(self, image_key):
        self.keys.append(image_key)
        return self.image_bytes


class FakePublisher:
    def __init__(self):
        self.payloads = []

    async def publish(self, payload):
        self.payloads.append(payload)
        return True


class LlmServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_process_preserves_event_and_camera_in_llm_payload(self):
        settings = SimpleNamespace(
            llm_model_name="llava:7b",
            ollama_url="http://ollama.test/api/generate",
        )
        fetcher = FakeFetcher()
        publisher = FakePublisher()
        msg = FakeMsg(
            {
                "event_id": "evt_123",
                "camera_id": "cam01",
                "source": "vision",
                "timestamp": "2026-05-26T21:00:00+09:00",
                "data": {"image_key": "events/evt_123/thumb.jpg"},
            }
        )

        original = nats_subscriber.analyze_image_bytes
        nats_subscriber.analyze_image_bytes = lambda *_args: (
            "A person is visible near the monitored area.",
            0.1,
        )
        try:
            await nats_subscriber._process(msg, settings, fetcher, publisher)
        finally:
            nats_subscriber.analyze_image_bytes = original

        self.assertEqual(fetcher.keys, ["events/evt_123/thumb.jpg"])
        self.assertEqual(len(publisher.payloads), 1)
        out = publisher.payloads[0]
        self.assertEqual(out["event_id"], "evt_123")
        self.assertEqual(out["camera_id"], "cam01")
        self.assertEqual(out["source"], "llm")
        self.assertEqual(out["data"]["model_name"], "llava:7b")
        self.assertEqual(
            out["data"]["summary"],
            "A person is visible near the monitored area.",
        )
        msg.ack.assert_awaited_once()

    async def test_process_acks_and_skips_when_image_key_missing(self):
        settings = SimpleNamespace(
            llm_model_name="llava:7b",
            ollama_url="http://ollama.test/api/generate",
        )
        fetcher = FakeFetcher()
        publisher = FakePublisher()
        msg = FakeMsg(
            {
                "event_id": "evt_123",
                "camera_id": "cam01",
                "source": "vision",
                "timestamp": "2026-05-26T21:00:00+09:00",
                "data": {},
            }
        )

        await nats_subscriber._process(msg, settings, fetcher, publisher)

        self.assertEqual(fetcher.keys, [])
        self.assertEqual(publisher.payloads, [])
        msg.ack.assert_awaited_once()


class CleanSummaryTests(unittest.TestCase):
    def test_clean_summary_extracts_summary_from_json(self):
        self.assertEqual(
            llm_client.clean_summary('{"summary": "A person walks through a crosswalk."}'),
            "A person walks through a crosswalk.",
        )

    def test_clean_summary_strips_plain_text(self):
        self.assertEqual(
            llm_client.clean_summary("  A person is standing near a doorway.  "),
            "A person is standing near a doorway.",
        )


if __name__ == "__main__":
    unittest.main()
