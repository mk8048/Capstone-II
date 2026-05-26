"""LLM Server settings loaded from .env via python-dotenv."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    nats_url: str
    nats_stream: str
    nats_vision_subject: str
    nats_llm_subject: str
    nats_vision_consumer: str
    nats_fetch_batch: int
    nats_fetch_timeout_seconds: float
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    minio_secure: bool
    ollama_url: str
    llm_model_name: str


def _to_bool(value: str) -> bool:
    return value.lower() == "true"


def load_settings() -> Settings:
    return Settings(
        nats_url=os.getenv("NATS_URL", "nats://localhost:4222"),
        nats_stream=os.getenv("NATS_STREAM", "CAPSTONE_EVENTS"),
        nats_vision_subject=os.getenv("NATS_VISION_SUBJECT", "cs.vision.control.detected"),
        nats_llm_subject=os.getenv("NATS_LLM_SUBJECT", "cs.llm.control.update"),
        nats_vision_consumer=os.getenv("NATS_VISION_CONSUMER", "llm-server-vision"),
        nats_fetch_batch=int(os.getenv("NATS_FETCH_BATCH", "1")),
        nats_fetch_timeout_seconds=float(os.getenv("NATS_FETCH_TIMEOUT_SECONDS", "5")),
        minio_endpoint=os.getenv("MINIO_ENDPOINT", "localhost:9000"),
        minio_access_key=os.getenv("MINIO_ACCESS_KEY", "minio_admin"),
        minio_secret_key=os.getenv("MINIO_SECRET_KEY", ""),
        minio_bucket=os.getenv("MINIO_BUCKET", "capstone2"),
        minio_secure=_to_bool(os.getenv("MINIO_SECURE", "false")),
        ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate"),
        llm_model_name=os.getenv("LLM_MODEL_NAME", "llava:7b"),
    )
