import json

import pytest
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.subscribers import llm_subscriber, vision_subscriber


class FakeMetadata:
    def __init__(self, num_delivered):
        self.num_delivered = num_delivered


class FakeMsg:
    def __init__(self, payload, deliveries=1):
        if isinstance(payload, bytes):
            self.data = payload
        else:
            self.data = json.dumps(payload).encode("utf-8")
        self.metadata = FakeMetadata(deliveries)
        self.acked = False
        self.nak_delay = None

    async def ack(self):
        self.acked = True

    async def nak(self, delay=None):
        self.nak_delay = delay


class FakeNatsConnection:
    def __init__(self):
        self.dlq = []

    async def publish_dlq(self, **kwargs):
        self.dlq.append(kwargs)


class FakeSession:
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


def vision_payload():
    return {
        "event_id": "evt_0001",
        "camera_id": "cam01",
        "event_type": "person_detected",
        "source": "vision",
        "timestamp": "2026-03-23T15:30:00+09:00",
        "data": {
            "object_count": 1,
            "max_confidence": 0.95,
            "image_key": "events/evt_0001/thumb.jpg",
            "objects": [
                {
                    "class_name": "person",
                    "confidence": 0.95,
                    "bbox": [100, 200, 50, 100],
                    "track_id": None,
                }
            ],
        },
    }


def llm_payload():
    return {
        "event_id": "evt_0001",
        "camera_id": "cam01",
        "event_type": "intrusion",
        "source": "llm",
        "timestamp": "2026-03-23T15:30:02+09:00",
        "data": {
            "model_name": "llava:7b",
            "summary": "summary",
            "object_state": "state",
            "action_description": "action",
            "risk_level": "caution",
            "recommended_action": "notify",
            "raw_response": {},
        },
    }


@pytest.mark.asyncio
async def test_vision_success_commits_and_acks(monkeypatch):
    async def save(session, payload):
        session.saved_event_id = payload.event_id
        return True

    session = FakeSession()
    fake_nats = FakeNatsConnection()
    monkeypatch.setattr(vision_subscriber, "nats_connection", fake_nats)
    monkeypatch.setattr(vision_subscriber, "async_session", lambda: session)
    monkeypatch.setattr(vision_subscriber, "create_detection_event_from_vision", save)
    msg = FakeMsg(vision_payload(), deliveries=1)

    await vision_subscriber._process(msg)

    assert session.committed is True
    assert session.rolled_back is False
    assert msg.acked is True
    assert msg.nak_delay is None
    assert fake_nats.dlq == []


@pytest.mark.asyncio
async def test_vision_invalid_json_goes_to_dlq_and_acks(monkeypatch):
    fake_nats = FakeNatsConnection()
    monkeypatch.setattr(vision_subscriber, "nats_connection", fake_nats)
    msg = FakeMsg(b"{not-json", deliveries=1)

    await vision_subscriber._process(msg)

    assert msg.acked is True
    assert msg.nak_delay is None
    assert fake_nats.dlq[0]["source_subject"] == settings.NATS_VISION_SUBJECT
    assert fake_nats.dlq[0]["deliveries"] == 1


@pytest.mark.asyncio
async def test_vision_integrity_error_naks_before_max_deliver(monkeypatch):
    async def fail_insert(session, payload):
        raise IntegrityError("insert", {}, Exception("fk"))

    fake_nats = FakeNatsConnection()
    monkeypatch.setattr(vision_subscriber, "nats_connection", fake_nats)
    monkeypatch.setattr(vision_subscriber, "async_session", lambda: FakeSession())
    monkeypatch.setattr(
        vision_subscriber, "create_detection_event_from_vision", fail_insert
    )
    msg = FakeMsg(vision_payload(), deliveries=settings.NATS_MAX_DELIVER - 1)

    await vision_subscriber._process(msg)

    assert msg.acked is False
    assert msg.nak_delay == settings.NATS_NAK_DELAY_SECONDS
    assert fake_nats.dlq == []


@pytest.mark.asyncio
async def test_vision_integrity_error_dlqs_at_max_deliver(monkeypatch):
    async def fail_insert(session, payload):
        raise IntegrityError("insert", {}, Exception("fk"))

    fake_nats = FakeNatsConnection()
    monkeypatch.setattr(vision_subscriber, "nats_connection", fake_nats)
    monkeypatch.setattr(vision_subscriber, "async_session", lambda: FakeSession())
    monkeypatch.setattr(
        vision_subscriber, "create_detection_event_from_vision", fail_insert
    )
    msg = FakeMsg(vision_payload(), deliveries=settings.NATS_MAX_DELIVER)

    await vision_subscriber._process(msg)

    assert msg.acked is True
    assert msg.nak_delay is None
    assert fake_nats.dlq[0]["reason"] == "missing_camera"


@pytest.mark.asyncio
async def test_llm_invalid_json_goes_to_dlq_and_acks(monkeypatch):
    fake_nats = FakeNatsConnection()
    monkeypatch.setattr(llm_subscriber, "nats_connection", fake_nats)
    msg = FakeMsg(b"{not-json", deliveries=1)

    await llm_subscriber._process(msg)

    assert msg.acked is True
    assert msg.nak_delay is None
    assert fake_nats.dlq[0]["source_subject"] == settings.NATS_LLM_SUBJECT
    assert fake_nats.dlq[0]["deliveries"] == 1


@pytest.mark.asyncio
async def test_llm_success_commits_and_acks(monkeypatch):
    async def save(session, payload):
        session.saved_event_id = payload.event_id

    session = FakeSession()
    fake_nats = FakeNatsConnection()
    monkeypatch.setattr(llm_subscriber, "nats_connection", fake_nats)
    monkeypatch.setattr(llm_subscriber, "async_session", lambda: session)
    monkeypatch.setattr(llm_subscriber, "create_llm_analysis_from_update", save)
    msg = FakeMsg(llm_payload(), deliveries=1)

    await llm_subscriber._process(msg)

    assert session.committed is True
    assert session.rolled_back is False
    assert msg.acked is True
    assert msg.nak_delay is None
    assert fake_nats.dlq == []


@pytest.mark.asyncio
async def test_llm_integrity_error_naks_before_max_deliver(monkeypatch):
    async def fail_insert(session, payload):
        raise IntegrityError("insert", {}, Exception("fk"))

    fake_nats = FakeNatsConnection()
    monkeypatch.setattr(llm_subscriber, "nats_connection", fake_nats)
    monkeypatch.setattr(llm_subscriber, "async_session", lambda: FakeSession())
    monkeypatch.setattr(llm_subscriber, "create_llm_analysis_from_update", fail_insert)
    msg = FakeMsg(llm_payload(), deliveries=settings.NATS_MAX_DELIVER - 1)

    await llm_subscriber._process(msg)

    assert msg.acked is False
    assert msg.nak_delay == settings.NATS_NAK_DELAY_SECONDS
    assert fake_nats.dlq == []


@pytest.mark.asyncio
async def test_llm_integrity_error_dlqs_at_max_deliver(monkeypatch):
    async def fail_insert(session, payload):
        raise IntegrityError("insert", {}, Exception("fk"))

    fake_nats = FakeNatsConnection()
    monkeypatch.setattr(llm_subscriber, "nats_connection", fake_nats)
    monkeypatch.setattr(llm_subscriber, "async_session", lambda: FakeSession())
    monkeypatch.setattr(llm_subscriber, "create_llm_analysis_from_update", fail_insert)
    msg = FakeMsg(llm_payload(), deliveries=settings.NATS_MAX_DELIVER)

    await llm_subscriber._process(msg)

    assert msg.acked is True
    assert msg.nak_delay is None
    assert fake_nats.dlq[0]["reason"] == "parent_event_not_found"
