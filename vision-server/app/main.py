"""Vision Server entry point. python -m app.main"""

import asyncio
import time

from app.config import load_settings
from app.detector import PersonDetector
from app.event_builder import build_event, make_event_id
from app.publisher import NatsPublisher
from app.storage import save_frame
from app.video_source import VideoSource


async def run() -> None:
    settings = load_settings()
    print(
        f"[vision] starting camera_id={settings.camera_id} "
        f"source={settings.video_source} device={settings.device}"
    )

    settings.output_dir.mkdir(parents=True, exist_ok=True)

    source = VideoSource(settings.video_source)
    detector = PersonDetector(
        settings.model_path, settings.device, settings.conf_threshold
    )
    publisher = NatsPublisher(settings.nats_url, settings.nats_subject)

    last_publish_ts = 0.0
    try:
        await publisher.connect()
        print(f"[vision] nats connected url={settings.nats_url} subject={settings.nats_subject}")
        while True:
            frame = await asyncio.to_thread(source.read)
            if frame is None:
                print("[vision] end of stream")
                break

            persons = await asyncio.to_thread(detector.detect_persons, frame)
            if not persons:
                continue

            now = time.monotonic()
            if now - last_publish_ts < settings.event_cooldown_seconds:
                continue

            event_id = make_event_id()
            image_key = save_frame(frame, settings.output_dir, event_id)
            payload = build_event(event_id, settings.camera_id, image_key, persons)
            ok = await publisher.publish(payload)
            if ok:
                last_publish_ts = now
                print(
                    f"[vision] event published event_id={event_id} "
                    f"objects={len(persons)} max_conf={payload['data']['max_confidence']}"
                )
            else:
                print(f"[vision] event dropped event_id={event_id} reason=publish_failed")
    except KeyboardInterrupt:
        print("[vision] interrupted")
    finally:
        source.release()
        await publisher.close()
        print("[vision] shutdown complete")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
