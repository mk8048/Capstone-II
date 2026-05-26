"""MinIO image fetcher. get_object by image_key -> bytes."""

from minio import Minio


class ImageFetcher:
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

    def fetch(self, image_key: str) -> bytes | None:
        resp = None
        try:
            resp = self.client.get_object(self.bucket, image_key)
            return resp.read()
        except Exception as e:
            print(f"[minio] fetch failed image_key={image_key} error={e}")
            return None
        finally:
            if resp is not None:
                resp.close()
                resp.release_conn()
