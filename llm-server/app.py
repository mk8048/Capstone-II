"""Manual debug endpoint. POST /analyze a local image_path and publish the result.

Optional: needs `fastapi` + `uvicorn` installed. Production flow is main.py (NATS).
Run: uvicorn app:app --port 8100
"""

import nats
from fastapi import FastAPI
from pydantic import BaseModel

from config import load_settings
from llm_client import analyze_image
from nats_subscriber import build_llm_payload
from nats_publisher import LlmPublisher

app = FastAPI()
settings = load_settings()


class AnalyzeRequest(BaseModel):
    image_path: str
    event_id: str
    camera_id: str


@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    summary = analyze_image(req.image_path, settings.llm_model_name, settings.ollama_url)
    payload = build_llm_payload(
        req.event_id, req.camera_id, settings.llm_model_name, summary
    )

    nc = await nats.connect(settings.nats_url)
    try:
        publisher = LlmPublisher(nc.jetstream(), settings.nats_llm_subject)
        await publisher.publish(payload)
    finally:
        await nc.drain()

    return {"status": "success", "message": payload}
