from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Camera(Base):
    __tablename__ = "cameras"

    camera_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    location: Mapped[Optional[str]] = mapped_column(String(256))
    stream_url: Mapped[Optional[str]] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DetectionEvent(Base):
    __tablename__ = "detection_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    camera_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cameras.camera_id")
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_type: Mapped[str] = mapped_column(String(64))
    image_key: Mapped[Optional[str]] = mapped_column(String(512))
    object_count: Mapped[int] = mapped_column(Integer, default=0)
    max_confidence: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default="created")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DetectedObject(Base):
    __tablename__ = "detected_objects"

    object_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("detection_events.event_id", ondelete="CASCADE"),
    )
    class_name: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[float] = mapped_column(Float)
    bbox_x: Mapped[int] = mapped_column(Integer)
    bbox_y: Mapped[int] = mapped_column(Integer)
    bbox_width: Mapped[int] = mapped_column(Integer)
    bbox_height: Mapped[int] = mapped_column(Integer)
    track_id: Mapped[Optional[str]] = mapped_column(String(64))
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)


class LLMAnalysis(Base):
    __tablename__ = "llm_analysis"

    analysis_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("detection_events.event_id", ondelete="CASCADE"),
    )
    model_name: Mapped[str] = mapped_column(String(128))
    summary: Mapped[Optional[str]] = mapped_column(Text)
    object_state: Mapped[Optional[str]] = mapped_column(Text)
    action_description: Mapped[Optional[str]] = mapped_column(Text)
    risk_level: Mapped[Optional[str]] = mapped_column(String(16))
    recommended_action: Mapped[Optional[str]] = mapped_column(Text)
    raw_response: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
