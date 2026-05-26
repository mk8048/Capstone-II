"""JetStream durable pull consumer for cs.vision.control.detected.

For each Vision detection event: fetch the frame from MinIO, summarize it with
LLaVA, and publish cs.llm.control.update with the same event_id. MVP error
handling is log-only: failures are logged and the message is acked/skipped.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone

from nats.errors import TimeoutError as NatsTimeoutError
from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy

from llm_client import analyze_image_bytes

KST = timezone(timedelta(hours=9))


def now_kst_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def build_llm_payload(event_id, camera_id, model_name, summary) -> dict:
    """Assemble cs.llm.control.update payload per docs/nats-schema.md §2."""
    return {
        "event_id": event_id,
        "camera_id": camera_id,
        "source": "llm",
        "timestamp": now_kst_iso(),
        "data": {
            "model_name": model_name,
            "summary": summary,
        },
    }


async def run(settings, js, fetcher, publisher, stop_event) -> None:
    # main-server owns the stream; retry until it exists (handles startup order).
    psub = None
    while psub is None and not stop_event.is_set():
        try:
            try:
                await js.consumer_info(settings.nats_stream, settings.nats_vision_consumer)
            except Exception:
                await js.add_consumer(
                    stream=settings.nats_stream,
                    config=ConsumerConfig(
                        durable_name=settings.nats_vision_consumer,
                        filter_subject=settings.nats_vision_subject,
                        ack_policy=AckPolicy.EXPLICIT,
                        deliver_policy=DeliverPolicy.NEW,
                    ),
                )
            psub = await js.pull_subscribe_bind(
                stream=settings.nats_stream,
                consumer=settings.nats_vision_consumer,
            )
        except Exception as e:
            print(f"[llm] pull_subscribe failed (stream not ready?): {e}; retry in 3s")
            await asyncio.sleep(3)
    if psub is None:
        return

    print(
        f"[llm] subscribed stream={settings.nats_stream} "
        f"consumer={settings.nats_vision_consumer} subject={settings.nats_vision_subject}"
    )

    while not stop_event.is_set():
        try:
            msgs = await psub.fetch(
                batch=settings.nats_fetch_batch,
                timeout=settings.nats_fetch_timeout_seconds,
            )
        except NatsTimeoutError:
            continue
        for msg in msgs:
            await _process(msg, settings, fetcher, publisher)


async def _process(msg, settings, fetcher, publisher) -> None:
    start = time.monotonic()

    try:
        payload = json.loads(msg.data.decode("utf-8"))
    except json.JSONDecodeError:
        print("[llm] skip: invalid json")
        await msg.ack()
        return

    event_id = payload.get("event_id")
    camera_id = payload.get("camera_id")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    image_key = data.get("image_key")

    if not event_id or not camera_id or not image_key:
        print(
            f"[llm] skip: missing fields event_id={event_id} "
            f"camera_id={camera_id} image_key={image_key}"
        )
        await msg.ack()
        return

    image_bytes = await asyncio.to_thread(fetcher.fetch, image_key)
    if image_bytes is None:
        print(f"[llm] skip: image fetch failed event_id={event_id} image_key={image_key}")
        await msg.ack()
        return

    try:
        summary, inference = await asyncio.to_thread(
            analyze_image_bytes,
            image_bytes,
            settings.llm_model_name,
            settings.ollama_url,
        )
    except Exception as e:
        print(f"[llm] skip: inference failed event_id={event_id} error={e}")
        await msg.ack()
        return

    out = build_llm_payload(event_id, camera_id, settings.llm_model_name, summary)
    ok = await publisher.publish(out)
    await msg.ack()

    total = time.monotonic() - start
    if ok:
        print(
            f"[llm] published event_id={event_id} "
            f"inference={inference:.2f}s total={total:.2f}s summary={summary!r}"
        )
    else:
        print(f"[llm] publish failed event_id={event_id} (acked anyway)")
