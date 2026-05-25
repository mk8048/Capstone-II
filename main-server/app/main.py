import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from app.api import events, health
from app.config import settings
from app.db import engine
from app.logging import setup_logging
from app.subscribers import llm_subscriber, vision_subscriber
from app.subscribers.nats_client import nats_connection


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info(f"main-server starting port={settings.MAIN_SERVER_PORT}")

    await nats_connection.connect()

    stop_event = asyncio.Event()
    tasks = [
        asyncio.create_task(vision_subscriber.run(stop_event), name="vision-subscriber"),
        asyncio.create_task(llm_subscriber.run(stop_event), name="llm-subscriber"),
    ]

    try:
        yield
    finally:
        logger.info("main-server shutting down")
        stop_event.set()
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await asyncio.wait_for(task, timeout=3)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        await nats_connection.close()
        await engine.dispose()
        logger.info("main-server shutdown complete")


app = FastAPI(title="main-server", lifespan=lifespan)
app.include_router(health.router)
app.include_router(events.router)
