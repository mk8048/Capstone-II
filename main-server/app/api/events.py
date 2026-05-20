from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session
from app.schemas import (
    EventDetail,
    EventSummary,
    LLMAnalysisResponse,
    ObjectResponse,
)
from app.services.event_service import get_event_detail, get_events

router = APIRouter()


@router.get("/events", response_model=list[EventSummary])
async def list_events(
    limit: int = Query(20, ge=1, le=100),
    camera_id: Optional[str] = None,
    status: Optional[str] = None,
    risk_level: Optional[str] = None,
) -> list[EventSummary]:
    async with async_session() as session:
        rows = await get_events(
            session,
            limit=limit,
            camera_id=camera_id,
            status=status,
            risk_level=risk_level,
        )
    return [
        EventSummary(
            event_id=event.event_id,
            camera_id=event.camera_id,
            occurred_at=event.occurred_at,
            event_type=event.event_type,
            image_key=event.image_key,
            object_count=event.object_count,
            max_confidence=event.max_confidence,
            status=event.status,
            risk_level=risk,
        )
        for event, risk in rows
    ]


@router.get("/events/{event_id}", response_model=EventDetail)
async def event_detail(event_id: str) -> EventDetail:
    async with async_session() as session:
        result = await get_event_detail(session, event_id)
    if result is None:
        raise HTTPException(status_code=404, detail="event not found")

    event, objects, latest = result
    return EventDetail(
        event_id=event.event_id,
        camera_id=event.camera_id,
        occurred_at=event.occurred_at,
        event_type=event.event_type,
        image_key=event.image_key,
        object_count=event.object_count,
        max_confidence=event.max_confidence,
        status=event.status,
        objects=[ObjectResponse.model_validate(o) for o in objects],
        latest_analysis=(
            LLMAnalysisResponse.model_validate(latest) if latest is not None else None
        ),
    )
