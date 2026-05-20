"""Video source wrapper. Accepts webcam index ('0'), file path, or RTSP URL."""

import cv2


class VideoSource:
    def __init__(self, source: str):
        if source.isdigit():
            self.cap = cv2.VideoCapture(int(source), cv2.CAP_DSHOW)
        else:
            self.cap = cv2.VideoCapture(source)
        if not self.cap.isOpened():
            raise RuntimeError(f"failed to open video source: {source}")

    def read(self):
        ok, frame = self.cap.read()
        if not ok:
            return None
        return frame

    def release(self) -> None:
        self.cap.release()
