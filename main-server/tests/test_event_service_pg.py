import asyncio
import socket
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url
from sqlalchemy import delete, insert, select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.db import async_session, engine
from app.models import Camera, DetectionEvent, DetectedObject, LLMAnalysis
from app.schemas import LLMPayload, VisionPayload
from app.services.event_service import (
    create_detection_event_from_vision,
    create_llm_analysis_from_update,
    get_event_detail,
    get_events,
)


PREFIX = "codex_pg_"
CAMERA_ID = f"{PREFIX}cam01"


@pytest_asyncio.fixture
async def pg_session():
    url = make_url(str(engine.url))
    host = url.host or "localhost"
    port = url.port or 5432
    try:
        with socket.create_connection((host, port), timeout=1):
            pass
    except OSError as exc:
        pytest.skip(f"PostgreSQL socket is not available: {host}:{port} ({exc})")

    try:
        conn = await asyncio.wait_for(engine.connect(), timeout=3)
        try:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=3)
        finally:
            await conn.close()
    except (OSError, OperationalError, TimeoutError, asyncio.TimeoutError) as exc:
        pytest.skip(f"PostgreSQL is not available: {exc}")

    async with async_session() as session:
        await cleanup(session)
        await session.execute(
            insert(Camera).values(
                camera_id=CAMERA_ID,
                name="Codex PG Test Camera",
                location="test",
                stream_url="samples/test.mp4",
                is_active=True,
            )
        )
        await session.commit()

        try:
            yield session
        finally:
            await session.rollback()
            await cleanup(session)
            await session.commit()
            await engine.dispose()


async def cleanup(session):
    event_ids = select(DetectionEvent.event_id).where(
        DetectionEvent.event_id.like(f"{PREFIX}%")
    )
    await session.execute(delete(LLMAnalysis).where(LLMAnalysis.event_id.in_(event_ids)))
    await session.execute(
        delete(DetectedObject).where(DetectedObject.event_id.in_(event_ids))
    )
    await session.execute(
        delete(DetectionEvent).where(DetectionEvent.event_id.like(f"{PREFIX}%"))
    )
    await session.execute(delete(Camera).where(Camera.camera_id.like(f"{PREFIX}%")))


def vision_payload(event_id=f"{PREFIX}evt_0001"):
    return VisionPayload.model_validate(
        {
            "event_id": event_id,
            "camera_id": CAMERA_ID,
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


def llm_payload(event_id=f"{PREFIX}evt_0001", risk_level="danger"):
    return LLMPayload.model_validate(
        {
            "event_id": event_id,
            "camera_id": CAMERA_ID,
            "event_type": "intrusion",
            "source": "llm",
            "timestamp": "2026-03-23T15:30:02+09:00",
            "data": {
                "model_name": "llava:7b",
                "summary": f"{risk_level} summary",
                "object_state": "state",
                "action_description": "action",
                "risk_level": risk_level,
                "recommended_action": "notify",
                "raw_response": {"risk": risk_level},
            },
        }
    )


@pytest.mark.asyncio
async def test_pg_create_detection_event_is_idempotent_and_keeps_objects_once(
    pg_session,
):
    payload = vision_payload()

    inserted_first = await create_detection_event_from_vision(pg_session, payload)
    await pg_session.commit()
    inserted_second = await create_detection_event_from_vision(pg_session, payload)
    await pg_session.commit()

    assert inserted_first is True
    assert inserted_second is False

    detail = await get_event_detail(pg_session, payload.event_id)
    assert detail is not None
    event, objects, latest = detail
    assert event.event_id == payload.event_id
    assert len(objects) == 2
    assert latest is None


@pytest.mark.asyncio
async def test_pg_llm_analysis_accumulates_and_latest_risk_filter_uses_latest(
    pg_session,
):
    payload = vision_payload(f"{PREFIX}evt_latest")
    await create_detection_event_from_vision(pg_session, payload)
    await pg_session.commit()

    await create_llm_analysis_from_update(
        pg_session, llm_payload(payload.event_id, risk_level="normal")
    )
    await pg_session.commit()
    await pg_session.execute(
        insert(LLMAnalysis).values(
            event_id=payload.event_id,
            model_name="llava:7b",
            summary="latest danger summary",
            risk_level="danger",
            raw_response={"risk": "danger"},
            created_at=datetime.now(timezone.utc) + timedelta(seconds=1),
        )
    )
    await pg_session.commit()

    danger_rows = await get_events(pg_session, risk_level="danger")
    normal_rows = await get_events(pg_session, risk_level="normal")
    detail = await get_event_detail(pg_session, payload.event_id)

    assert [row[0].event_id for row in danger_rows] == [payload.event_id]
    assert normal_rows == []
    assert detail is not None
    event, objects, latest = detail
    assert event.status == "analyzed"
    assert len(objects) == 2
    assert latest is not None
    assert latest.risk_level == "danger"


@pytest.mark.asyncio
async def test_pg_llm_orphan_raises_integrity_error(pg_session):
    with pytest.raises(IntegrityError):
        await create_llm_analysis_from_update(
            pg_session, llm_payload(f"{PREFIX}missing_parent")
        )
    await pg_session.rollback()
