import pytest

from app.schemas import LLMPayload, VisionPayload
from app.services.event_service import (
    create_detection_event_from_vision,
    create_llm_analysis_from_update,
)


class FakeResult:
    def __init__(self, rowcount):
        self.rowcount = rowcount


class FakeSession:
    def __init__(self, rowcount=1):
        self.rowcount = rowcount
        self.executed = []
        self.added = []
        self.flushed = False

    async def execute(self, statement, params=None):
        self.executed.append((statement, params))
        return FakeResult(self.rowcount)

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        self.flushed = True


def vision_payload(event_id="evt_0001"):
    return VisionPayload.model_validate(
        {
            "event_id": event_id,
            "camera_id": "cam01",
            "event_type": "person_detected",
            "source": "vision",
            "timestamp": "2026-03-23T15:30:00+09:00",
            "data": {
                "object_count": 2,
                "max_confidence": 0.95,
                "image_key": f"events/{event_id}/thumb.jpg",
                "objects": [
                    {
                        "class_name": "person",
                        "confidence": 0.95,
                        "bbox": [100, 200, 50, 100],
                        "track_id": None,
                    },
                    {
                        "class_name": "bag",
                        "confidence": 0.72,
                        "bbox": [180, 250, 30, 40],
                        "track_id": "track-1",
                    },
                ],
            },
        }
    )


def llm_payload(event_id="evt_0001"):
    return LLMPayload.model_validate(
        {
            "event_id": event_id,
            "camera_id": "cam01",
            "event_type": "intrusion",
            "source": "llm",
            "timestamp": "2026-03-23T15:30:02+09:00",
            "data": {
                "model_name": "llava:7b",
                "summary": "summary",
                "object_state": "state",
                "action_description": "action",
                "risk_level": "danger",
                "recommended_action": "notify",
                "raw_response": {"raw": True},
            },
        }
    )


@pytest.mark.asyncio
async def test_create_detection_event_inserts_objects_when_event_is_new():
    session = FakeSession(rowcount=1)

    inserted = await create_detection_event_from_vision(session, vision_payload())

    assert inserted is True
    assert len(session.executed) == 2
    object_rows = session.executed[1][1]
    assert object_rows == [
        {
            "event_id": "evt_0001",
            "class_name": "person",
            "confidence": 0.95,
            "bbox_x": 100,
            "bbox_y": 200,
            "bbox_width": 50,
            "bbox_height": 100,
            "track_id": None,
        },
        {
            "event_id": "evt_0001",
            "class_name": "bag",
            "confidence": 0.72,
            "bbox_x": 180,
            "bbox_y": 250,
            "bbox_width": 30,
            "bbox_height": 40,
            "track_id": "track-1",
        },
    ]


@pytest.mark.asyncio
async def test_create_detection_event_skips_objects_when_event_is_duplicate():
    session = FakeSession(rowcount=0)

    inserted = await create_detection_event_from_vision(session, vision_payload())

    assert inserted is False
    assert len(session.executed) == 1


@pytest.mark.asyncio
async def test_create_llm_analysis_adds_analysis_flushes_and_updates_event():
    session = FakeSession()

    await create_llm_analysis_from_update(session, llm_payload())

    assert len(session.added) == 1
    assert session.added[0].event_id == "evt_0001"
    assert session.added[0].model_name == "llava:7b"
    assert session.added[0].risk_level == "danger"
    assert session.flushed is True
    assert len(session.executed) == 1
