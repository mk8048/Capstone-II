"""Vision Server settings loaded from .env via python-dotenv."""

import os
from dataclasses import dataclass

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
    event_cooldown_seconds: float
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    minio_secure: bool
    stream_enabled: bool
    mediamtx_rtsp_url: str
    stream_fps: int
    stream_width: int
    stream_height: int
    stream_bitrate: str
    stream_overlay: bool
    ffmpeg_path: str
    ffmpeg_log_path: str


def _to_bool(value: str) -> bool:
    return value.lower() == "true"


def load_settings() -> Settings:
    return Settings(
        nats_url=os.getenv("NATS_URL", "nats://localhost:4222"),
        nats_subject=os.getenv("NATS_SUBJECT", "cs.vision.control.detected"),
        camera_id=os.getenv("CAMERA_ID", "cam01"),
        video_source=os.getenv("VIDEO_SOURCE", "0"),
        model_path=os.getenv("MODEL_PATH", "yolov8n.pt"),
        conf_threshold=float(os.getenv("CONF_THRESHOLD", "0.5")),
        device=os.getenv("DEVICE", "cuda"),
        event_cooldown_seconds=float(os.getenv("EVENT_COOLDOWN_SECONDS", "3")),
        minio_endpoint=os.getenv("MINIO_ENDPOINT", "localhost:9000"),
        minio_access_key=os.getenv("MINIO_ACCESS_KEY", "minio_admin"),
        minio_secret_key=os.getenv("MINIO_SECRET_KEY", ""),
        minio_bucket=os.getenv("MINIO_BUCKET", "capstone2"),
        minio_secure=_to_bool(os.getenv("MINIO_SECURE", "false")),
        stream_enabled=_to_bool(os.getenv("STREAM_ENABLED", "false")),
        mediamtx_rtsp_url=os.getenv("MEDIAMTX_RTSP_URL", "rtsp://127.0.0.1:8554/cam01"),
        stream_fps=int(os.getenv("STREAM_FPS", "30")),
        stream_width=int(os.getenv("STREAM_WIDTH", "0")),
        stream_height=int(os.getenv("STREAM_HEIGHT", "0")),
        stream_bitrate=os.getenv("STREAM_BITRATE", "2500k"),
        stream_overlay=_to_bool(os.getenv("STREAM_OVERLAY", "true")),
        ffmpeg_path=os.getenv("FFMPEG_PATH", "ffmpeg"),
        ffmpeg_log_path=os.getenv("FFMPEG_LOG_PATH", ""),
    )
