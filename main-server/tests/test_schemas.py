from pydantic import ValidationError

from app.schemas import LLMPayload, VisionPayload


def test_vision_payload_accepts_documented_shape():
    payload = VisionPayload.model_validate(
        {
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
    )

    assert payload.event_id == "evt_0001"
    assert payload.data.objects[0].bbox == [100, 200, 50, 100]


def test_vision_payload_rejects_invalid_bbox_length():
    try:
        VisionPayload.model_validate(
            {
                "event_id": "evt_0001",
                "camera_id": "cam01",
                "event_type": "person_detected",
                "source": "vision",
                "timestamp": "2026-03-23T15:30:00+09:00",
                "data": {
                    "object_count": 1,
                    "objects": [
                        {
                            "class_name": "person",
                            "confidence": 0.95,
                            "bbox": [100, 200, 50],
                        }
                    ],
                },
            }
        )
    except ValidationError as exc:
        assert "bbox" in str(exc)
    else:
        raise AssertionError("expected ValidationError")


def test_llm_payload_accepts_model_name_field():
    payload = LLMPayload.model_validate(
        {
            "event_id": "evt_0001",
            "camera_id": "cam01",
            "event_type": "intrusion",
            "source": "llm",
            "timestamp": "2026-03-23T15:30:02+09:00",
            "data": {
                "model_name": "llava:7b",
                "summary": "A person appears to be entering the monitored area.",
                "object_state": "한 명의 사람이 출입구를 통과 중",
                "action_description": "걸어서 실내로 진입",
                "risk_level": "caution",
                "recommended_action": "보안 요원에게 통보",
                "raw_response": {"ok": True},
            },
        }
    )

    assert payload.data.model_name == "llava:7b"
    assert payload.data.risk_level == "caution"


def test_llm_payload_accepts_minimal_documented_shape():
    payload = LLMPayload.model_validate(
        {
            "event_id": "evt_0001",
            "camera_id": "cam01",
            "source": "llm",
            "timestamp": "2026-03-23T15:30:02+09:00",
            "data": {
                "model_name": "llava:7b",
                "summary": "A person appears to be entering the monitored area.",
            },
        }
    )

    assert payload.event_type is None
    assert payload.data.model_name == "llava:7b"
    assert payload.data.summary == "A person appears to be entering the monitored area."
