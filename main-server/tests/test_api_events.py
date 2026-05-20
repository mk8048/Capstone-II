from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import events as events_api


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def event_row(event_id="evt_0001", status="created"):
    return SimpleNamespace(
        event_id=event_id,
        camera_id="cam01",
        occurred_at=datetime(2026, 3, 23, 15, 30, tzinfo=timezone.utc),
        event_type="person_detected",
        image_key=f"events/{event_id}/thumb.jpg",
        object_count=1,
        max_confidence=0.95,
        status=status,
    )


def object_row():
    return SimpleNamespace(
        class_name="person",
        confidence=0.95,
        bbox_x=100,
        bbox_y=200,
        bbox_width=50,
        bbox_height=100,
        track_id=None,
    )


def analysis_row():
    return SimpleNamespace(
        model_name="llava:7b",
        summary="summary",
        object_state="state",
        action_description="action",
        risk_level="caution",
        recommended_action="notify",
        created_at=datetime(2026, 3, 23, 15, 31, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_list_events_maps_service_rows(monkeypatch):
    async def fake_get_events(session, **kwargs):
        assert kwargs["limit"] == 10
        assert kwargs["camera_id"] == "cam01"
        assert kwargs["status"] == "analyzed"
        assert kwargs["risk_level"] == "danger"
        return [(event_row(status="analyzed"), "danger")]

    monkeypatch.setattr(events_api, "async_session", lambda: FakeSession())
    monkeypatch.setattr(events_api, "get_events", fake_get_events)

    result = await events_api.list_events(
        limit=10,
        camera_id="cam01",
        status="analyzed",
        risk_level="danger",
    )

    assert len(result) == 1
    assert result[0].event_id == "evt_0001"
    assert result[0].risk_level == "danger"


@pytest.mark.asyncio
async def test_event_detail_maps_service_result(monkeypatch):
    async def fake_get_event_detail(session, event_id):
        assert event_id == "evt_0001"
        return event_row(status="analyzed"), [object_row()], analysis_row()

    monkeypatch.setattr(events_api, "async_session", lambda: FakeSession())
    monkeypatch.setattr(events_api, "get_event_detail", fake_get_event_detail)

    result = await events_api.event_detail("evt_0001")

    assert result.event_id == "evt_0001"
    assert result.status == "analyzed"
    assert len(result.objects) == 1
    assert result.objects[0].bbox_width == 50
    assert result.latest_analysis is not None
    assert result.latest_analysis.risk_level == "caution"


@pytest.mark.asyncio
async def test_event_detail_returns_404_when_missing(monkeypatch):
    async def fake_get_event_detail(session, event_id):
        return None

    monkeypatch.setattr(events_api, "async_session", lambda: FakeSession())
    monkeypatch.setattr(events_api, "get_event_detail", fake_get_event_detail)

    with pytest.raises(HTTPException) as exc:
        await events_api.event_detail("missing")

    assert exc.value.status_code == 404
    assert exc.value.detail == "event not found"
