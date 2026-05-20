from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DetectedObject, DetectionEvent, LLMAnalysis
from app.schemas import LLMPayload, VisionPayload


async def create_detection_event_from_vision(
    session: AsyncSession, payload: VisionPayload
) -> bool:
    """Insert a Vision-originated event and its objects.

    Returns True if a new row was inserted, False if event_id already existed.
    Raises IntegrityError on missing camera_id FK — caller decides NAK/DLQ.
    """
    stmt = (
        pg_insert(DetectionEvent)
        .values(
            event_id=payload.event_id,
            camera_id=payload.camera_id,
            occurred_at=payload.timestamp,
            event_type=payload.event_type,
            image_key=payload.data.image_key,
            object_count=payload.data.object_count,
            max_confidence=payload.data.max_confidence,
            status="created",
        )
        .on_conflict_do_nothing(index_elements=["event_id"])
    )
    result = await session.execute(stmt)
    inserted = (result.rowcount or 0) > 0

    if inserted and payload.data.objects:
        await session.execute(
            DetectedObject.__table__.insert(),
            [
                {
                    "event_id": payload.event_id,
                    "class_name": obj.class_name,
                    "confidence": obj.confidence,
                    "bbox_x": obj.bbox[0],
                    "bbox_y": obj.bbox[1],
                    "bbox_width": obj.bbox[2],
                    "bbox_height": obj.bbox[3],
                    "track_id": obj.track_id,
                }
                for obj in payload.data.objects
            ],
        )
    return inserted


async def create_llm_analysis_from_update(
    session: AsyncSession, payload: LLMPayload
) -> None:
    """Insert an LLM analysis row and mark the parent event as analyzed.

    Raises IntegrityError if the parent event_id does not exist.
    No parent pre-check: FK violation is the signal to NAK/retry.
    """
    session.add(
        LLMAnalysis(
            event_id=payload.event_id,
            model_name=payload.data.model_name,
            summary=payload.data.summary,
            object_state=payload.data.object_state,
            action_description=payload.data.action_description,
            risk_level=payload.data.risk_level,
            recommended_action=payload.data.recommended_action,
            raw_response=payload.data.raw_response,
        )
    )
    # Force FK check now so caller can catch IntegrityError before commit
    await session.flush()

    await session.execute(
        update(DetectionEvent)
        .where(DetectionEvent.event_id == payload.event_id)
        .values(status="analyzed")
    )


async def get_events(
    session: AsyncSession,
    limit: int = 20,
    camera_id: Optional[str] = None,
    status: Optional[str] = None,
    risk_level: Optional[str] = None,
) -> list[tuple[DetectionEvent, Optional[str]]]:
    """Returns (event, latest_risk_level) tuples ordered by occurred_at desc."""
    latest_subq = (
        select(LLMAnalysis.event_id, LLMAnalysis.risk_level)
        .distinct(LLMAnalysis.event_id)
        .order_by(LLMAnalysis.event_id, LLMAnalysis.created_at.desc())
        .subquery()
    )

    stmt = (
        select(DetectionEvent, latest_subq.c.risk_level)
        .outerjoin(latest_subq, latest_subq.c.event_id == DetectionEvent.event_id)
        .order_by(DetectionEvent.occurred_at.desc())
        .limit(limit)
    )
    if camera_id:
        stmt = stmt.where(DetectionEvent.camera_id == camera_id)
    if status:
        stmt = stmt.where(DetectionEvent.status == status)
    if risk_level:
        stmt = stmt.where(latest_subq.c.risk_level == risk_level)

    result = await session.execute(stmt)
    return [(row[0], row[1]) for row in result.all()]


async def get_event_detail(
    session: AsyncSession, event_id: str
) -> Optional[tuple[DetectionEvent, list[DetectedObject], Optional[LLMAnalysis]]]:
    event = await session.get(DetectionEvent, event_id)
    if event is None:
        return None

    objects_result = await session.execute(
        select(DetectedObject).where(DetectedObject.event_id == event_id)
    )
    objects = list(objects_result.scalars().all())

    latest_result = await session.execute(
        select(LLMAnalysis)
        .where(LLMAnalysis.event_id == event_id)
        .order_by(LLMAnalysis.created_at.desc())
        .limit(1)
    )
    latest = latest_result.scalar_one_or_none()

    return event, objects, latest
