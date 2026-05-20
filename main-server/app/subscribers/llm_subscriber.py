import asyncio
import json

from loguru import logger
from nats.aio.msg import Msg
from nats.errors import TimeoutError as NatsTimeoutError
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.db import async_session
from app.schemas import LLMPayload
from app.services.event_service import create_llm_analysis_from_update
from app.subscribers.nats_client import nats_connection


async def run(stop_event: asyncio.Event) -> None:
    """Background loop: fetch LLM messages from JetStream and process them."""
    assert nats_connection.js is not None
    psub = await nats_connection.js.pull_subscribe_bind(
        consumer=settings.NATS_LLM_CONSUMER,
        stream=settings.NATS_STREAM,
    )
    logger.info(f"llm subscriber bound consumer={settings.NATS_LLM_CONSUMER}")

    while not stop_event.is_set():
        try:
            msgs = await psub.fetch(
                batch=settings.NATS_FETCH_BATCH,
                timeout=settings.NATS_FETCH_TIMEOUT_SECONDS,
            )
        except NatsTimeoutError:
            continue
        for msg in msgs:
            await _process(msg)


async def _process(msg: Msg) -> None:
    deliveries = msg.metadata.num_delivered

    try:
        raw = json.loads(msg.data.decode("utf-8"))
        payload = LLMPayload.model_validate(raw)
    except (json.JSONDecodeError, ValidationError) as e:
        logger.error(f"llm validation_error reason={e}")
        await nats_connection.publish_dlq(
            source_subject=settings.NATS_LLM_SUBJECT,
            reason=f"validation_error: {e.__class__.__name__}",
            deliveries=deliveries,
            payload=msg.data,
        )
        await msg.ack()
        return

    async with async_session() as session:
        try:
            await create_llm_analysis_from_update(session, payload)
            await session.commit()
        except IntegrityError:
            await session.rollback()
            logger.warning(
                f"llm parent_not_found event_id={payload.event_id} "
                f"deliveries={deliveries}"
            )
            if deliveries >= settings.NATS_MAX_DELIVER:
                await nats_connection.publish_dlq(
                    source_subject=settings.NATS_LLM_SUBJECT,
                    reason="parent_event_not_found",
                    deliveries=deliveries,
                    payload=msg.data,
                )
                await msg.ack()
            else:
                await msg.nak(delay=settings.NATS_NAK_DELAY_SECONDS)
            return
        except Exception as e:
            await session.rollback()
            logger.exception(f"llm unexpected_error event_id={payload.event_id}")
            if deliveries >= settings.NATS_MAX_DELIVER:
                await nats_connection.publish_dlq(
                    source_subject=settings.NATS_LLM_SUBJECT,
                    reason=f"db_error: {e.__class__.__name__}",
                    deliveries=deliveries,
                    payload=msg.data,
                )
                await msg.ack()
            else:
                await msg.nak(delay=settings.NATS_NAK_DELAY_SECONDS)
            return

    await msg.ack()
    logger.info(
        f"llm saved event_id={payload.event_id} "
        f"risk_level={payload.data.risk_level}"
    )
