import json
from datetime import datetime, timezone
from typing import Optional

import nats
from loguru import logger
from nats.aio.client import Client as NATS
from nats.js import JetStreamContext
from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy
from nats.js.errors import BadRequestError

from app.config import settings


class NatsConnection:
    """Holds the NATS connection, JetStream context, and ensures streams/consumers."""

    def __init__(self) -> None:
        self.nc: Optional[NATS] = None
        self.js: Optional[JetStreamContext] = None

    async def connect(self) -> None:
        self.nc = await nats.connect(settings.NATS_URL)
        self.js = self.nc.jetstream()
        await self._ensure_stream(
            settings.NATS_STREAM,
            [settings.NATS_VISION_SUBJECT, settings.NATS_LLM_SUBJECT],
        )
        await self._ensure_stream(
            settings.NATS_DLQ_STREAM,
            [settings.NATS_DLQ_SUBJECT],
        )
        await self._ensure_consumer(
            settings.NATS_STREAM,
            settings.NATS_VISION_CONSUMER,
            settings.NATS_VISION_SUBJECT,
        )
        await self._ensure_consumer(
            settings.NATS_STREAM,
            settings.NATS_LLM_CONSUMER,
            settings.NATS_LLM_SUBJECT,
        )

    async def close(self) -> None:
        if self.nc is None:
            return
        await self.nc.drain()
        await self.nc.close()

    async def _ensure_stream(self, name: str, subjects: list[str]) -> None:
        assert self.js is not None
        try:
            await self.js.add_stream(name=name, subjects=subjects)
            logger.info(f"stream created name={name} subjects={subjects}")
        except BadRequestError as e:
            logger.warning(
                f"stream add returned existing/conflict name={name} reason={e}"
            )

    async def _ensure_consumer(
        self, stream: str, durable: str, filter_subject: str
    ) -> None:
        assert self.js is not None
        config = ConsumerConfig(
            durable_name=durable,
            filter_subject=filter_subject,
            ack_policy=AckPolicy.EXPLICIT,
            deliver_policy=DeliverPolicy.ALL,
            max_deliver=settings.NATS_MAX_DELIVER,
            ack_wait=settings.NATS_ACK_WAIT_SECONDS,
        )
        try:
            await self.js.add_consumer(stream=stream, config=config)
            logger.info(f"consumer created stream={stream} durable={durable}")
        except BadRequestError as e:
            logger.warning(
                f"consumer add returned existing/conflict stream={stream} "
                f"durable={durable} reason={e}"
            )

    async def publish_dlq(
        self, source_subject: str, reason: str, deliveries: int, payload: bytes
    ) -> None:
        assert self.js is not None
        try:
            original = json.loads(payload.decode("utf-8"))
        except Exception:
            original = {"raw": payload.decode("utf-8", errors="replace")}
        envelope = {
            "source_subject": source_subject,
            "reason": reason,
            "deliveries": deliveries,
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "payload": original,
        }
        await self.js.publish(
            settings.NATS_DLQ_SUBJECT,
            json.dumps(envelope).encode("utf-8"),
        )
        logger.warning(
            f"dlq published source={source_subject} reason={reason} "
            f"deliveries={deliveries}"
        )


nats_connection = NatsConnection()
