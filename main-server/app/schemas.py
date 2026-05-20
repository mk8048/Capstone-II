from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class VisionObject(BaseModel):
    class_name: str
    confidence: float
    bbox: list[int] = Field(min_length=4, max_length=4)
    track_id: Optional[str] = None


class VisionData(BaseModel):
    object_count: int
    max_confidence: Optional[float] = None
    image_key: Optional[str] = None
    objects: list[VisionObject] = []


class VisionPayload(BaseModel):
    event_id: str
    camera_id: str
    event_type: str
    source: str
    timestamp: datetime
    data: VisionData


class LLMData(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_name: str
    summary: Optional[str] = None
    object_state: Optional[str] = None
    action_description: Optional[str] = None
    risk_level: Optional[str] = None
    recommended_action: Optional[str] = None
    raw_response: dict[str, Any] = {}


class LLMPayload(BaseModel):
    event_id: str
    camera_id: str
    event_type: Optional[str] = None
    source: str
    timestamp: datetime
    data: LLMData


class ObjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    class_name: str
    confidence: float
    bbox_x: int
    bbox_y: int
    bbox_width: int
    bbox_height: int
    track_id: Optional[str] = None


class LLMAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    model_name: str
    summary: Optional[str] = None
    object_state: Optional[str] = None
    action_description: Optional[str] = None
    risk_level: Optional[str] = None
    recommended_action: Optional[str] = None
    created_at: datetime


class EventSummary(BaseModel):
    event_id: str
    camera_id: str
    occurred_at: datetime
    event_type: str
    image_key: Optional[str] = None
    object_count: int
    max_confidence: Optional[float] = None
    status: str
    risk_level: Optional[str] = None


class EventDetail(BaseModel):
    event_id: str
    camera_id: str
    occurred_at: datetime
    event_type: str
    image_key: Optional[str] = None
    object_count: int
    max_confidence: Optional[float] = None
    status: str
    objects: list[ObjectResponse]
    latest_analysis: Optional[LLMAnalysisResponse] = None
