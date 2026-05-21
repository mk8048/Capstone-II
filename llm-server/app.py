from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
import asyncio

from llm_client import analyze_image
from nats_publisher import publish_message

app = FastAPI()


class AnalyzeRequest(BaseModel):
    image_path: str
    event_id: str
    camera_id: str


@app.post("/analyze")
async def analyze(req: AnalyzeRequest):

    summary = analyze_image(
        req.image_path,
        "llava:7b"
    )

    message = {
        "event_id": req.event_id,
        "camera_id": req.camera_id,
        "source": "llm",
        "timestamp": datetime.now().astimezone().isoformat(),
        "data": {
            "model_name": "llava:7b",
            "summary": summary
        }
    }

    await publish_message(message)

    return {
        "status": "success",
        "message": message
    }