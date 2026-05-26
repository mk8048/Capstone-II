"""LLM Server entrypoint. NATS-driven: subscribe Vision events, analyze, publish.

Run: python main.py
"""

import asyncio
import signal

import nats

import nats_subscriber
from config import load_settings
from minio_client import ImageFetcher
from nats_publisher import LlmPublisher


async def run() -> None:
    settings = load_settings()
    print(
        f"[llm] starting model={settings.llm_model_name} "
        f"ollama={settings.ollama_url} minio={settings.minio_endpoint}"
    )

    fetcher = ImageFetcher(
        settings.minio_endpoint,
        settings.minio_access_key,
        settings.minio_secret_key,
        settings.minio_bucket,
        settings.minio_secure,
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, AttributeError):
            # Windows ProactorEventLoop doesn't support signal handlers;
            # KeyboardInterrupt below handles Ctrl+C there.
            pass

    nc = await nats.connect(settings.nats_url)
    js = nc.jetstream()
    publisher = LlmPublisher(js, settings.nats_llm_subject)
    print(f"[llm] nats connected url={settings.nats_url} publish={settings.nats_llm_subject}")

    try:
        await nats_subscriber.run(settings, js, fetcher, publisher, stop_event)
    except KeyboardInterrupt:
        pass
    finally:
        await nc.drain()
        print("[llm] shutdown complete")


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
