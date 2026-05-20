"""Vision Server settings loaded from .env via python-dotenv."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    nats_url: str
    nats_subject: str
    camera_id: str
    video_source: str
    model_path: str
    conf_threshold: float
    device: str
    output_dir: Path
    event_cooldown_seconds: float


def load_settings() -> Settings:
    return Settings(
        nats_url=os.getenv("NATS_URL", "nats://localhost:4222"),
        nats_subject=os.getenv("NATS_SUBJECT", "cs.vision.control.detected"),
        camera_id=os.getenv("CAMERA_ID", "cam01"),
        video_source=os.getenv("VIDEO_SOURCE", "0"),
        model_path=os.getenv("MODEL_PATH", "yolov8n.pt"),
        conf_threshold=float(os.getenv("CONF_THRESHOLD", "0.5")),
        device=os.getenv("DEVICE", "cuda"),
        output_dir=Path(os.getenv("OUTPUT_DIR", "output")),
        event_cooldown_seconds=float(os.getenv("EVENT_COOLDOWN_SECONDS", "3")),
    )
