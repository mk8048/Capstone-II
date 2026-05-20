"""MinIO frame uploader. In-memory JPEG encode → put_object."""

from io import BytesIO

import cv2
from minio import Minio


class FrameUploader:
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool,
    ):
        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self.bucket = bucket

    def upload(self, frame, event_id: str) -> str | None:
        object_name = f"events/{event_id}/thumb.jpg"
        ok, buf = cv2.imencode(".jpg", frame)
        if not ok:
            print(f"[storage] jpeg encode failed event_id={event_id}")
            return None
        data = buf.tobytes()
        try:
            self.client.put_object(
                self.bucket,
                object_name,
                BytesIO(data),
                length=len(data),
                content_type="image/jpeg",
            )
            return object_name
        except Exception as e:
            print(f"[storage] upload failed event_id={event_id} error={e}")
            return None
