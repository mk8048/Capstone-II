"""Vision Server entry point. python -m app.main"""

import asyncio
import time

from app.config import load_settings
from app.detector import PersonDetector
from app.event_builder import build_event, make_event_id
from app.publisher import NatsPublisher
from app.storage import FrameUploader
from app.stream_publisher import FfmpegRtspPublisher, draw_overlay
from app.video_source import VideoSource


async def run() -> None:
    settings = load_settings()
    print(
        f"[vision] starting camera_id={settings.camera_id} "
        f"source={settings.video_source} device={settings.device}"
    )

    source = VideoSource(settings.video_source)
    detector = PersonDetector(
        settings.model_path, settings.device, settings.conf_threshold
    )
    uploader = FrameUploader(
        settings.minio_endpoint,
        settings.minio_access_key,
        settings.minio_secret_key,
        settings.minio_bucket,
        settings.minio_secure,
    )
    publisher = NatsPublisher(settings.nats_url, settings.nats_subject)

    stream_publisher: FfmpegRtspPublisher | None = None
    if settings.stream_enabled:
        stream_publisher = FfmpegRtspPublisher(
            rtsp_url=settings.mediamtx_rtsp_url,
            fps=settings.stream_fps,
            bitrate=settings.stream_bitrate,
            ffmpeg_path=settings.ffmpeg_path,
            log_path=settings.ffmpeg_log_path,
            width=settings.stream_width,
            height=settings.stream_height,
        )

    last_publish_ts = 0.0
    try:
        await publisher.connect()
        print(f"[vision] nats connected url={settings.nats_url} subject={settings.nats_subject}")
        print(f"[vision] minio target endpoint={settings.minio_endpoint} bucket={settings.minio_bucket}")
        if stream_publisher is not None:
            print(f"[vision] stream enabled rtsp={settings.mediamtx_rtsp_url} overlay={settings.stream_overlay}")
        else:
            print("[vision] stream disabled")
        while True:
            frame = await asyncio.to_thread(source.read)
            if frame is None:
                print("[vision] end of stream")
                break

            persons = await asyncio.to_thread(detector.detect_persons, frame)

            if stream_publisher is not None and stream_publisher.alive:
                if settings.stream_overlay and persons:
                    stream_frame = frame.copy()
                    draw_overlay(stream_frame, persons)
                else:
                    stream_frame = frame
                await asyncio.to_thread(stream_publisher.write, stream_frame)

            if not persons:
                continue

            now = time.monotonic()
            if now - last_publish_ts < settings.event_cooldown_seconds:
                continue

            event_id = make_event_id()
            image_key = await asyncio.to_thread(uploader.upload, frame, event_id)
            if image_key is None:
                print(f"[vision] event dropped event_id={event_id} reason=upload_failed")
                continue

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
        if stream_publisher is not None:
            stream_publisher.close()
        print("[vision] shutdown complete")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
