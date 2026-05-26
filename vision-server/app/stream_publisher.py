"""ffmpeg RTSP publisher for MediaMTX. Lazy init on first write."""

import subprocess

import cv2


def draw_overlay(frame, persons: list[dict]) -> None:
    for p in persons:
        x, y, w, h = p["bbox"]
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        label = f"person {p['confidence']:.2f}"
        cv2.putText(
            frame, label, (x, max(y - 6, 0)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA,
        )


class FfmpegRtspPublisher:
    def __init__(
        self,
        rtsp_url: str,
        fps: int,
        bitrate: str,
        ffmpeg_path: str,
        log_path: str,
        width: int = 0,
        height: int = 0,
    ):
        if (width > 0) != (height > 0):
            raise ValueError(
                "STREAM_WIDTH and STREAM_HEIGHT must both be 0 (auto from first frame) "
                f"or both positive (forced resize). got width={width}, height={height}"
            )
        self.rtsp_url = rtsp_url
        self.fps = fps
        self.bitrate = bitrate
        self.ffmpeg_path = ffmpeg_path
        self.log_path = log_path
        self.force_width = width
        self.force_height = height
        self.resize = width > 0 and height > 0
        self.proc: subprocess.Popen | None = None
        self.stderr_file = None
        self.stream_width = 0
        self.stream_height = 0
        self.alive = True

    def _start(self, frame_width: int, frame_height: int) -> None:
        if self.resize:
            self.stream_width, self.stream_height = self.force_width, self.force_height
        else:
            self.stream_width, self.stream_height = frame_width, frame_height

        cmd = [
            self.ffmpeg_path,
            "-loglevel", "info",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{self.stream_width}x{self.stream_height}",
            "-r", str(self.fps),
            "-i", "pipe:0",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-g", str(self.fps * 2),
            "-b:v", self.bitrate,
            "-f", "rtsp",
            "-rtsp_transport", "tcp",
            self.rtsp_url,
        ]
        if self.log_path:
            self.stderr_file = open(self.log_path, "wb")
            stderr = self.stderr_file
        else:
            stderr = subprocess.DEVNULL

        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=stderr)
        print(
            f"[stream] ffmpeg started size={self.stream_width}x{self.stream_height} "
            f"fps={self.fps} bitrate={self.bitrate} rtsp={self.rtsp_url}"
        )

    def write(self, frame) -> bool:
        if not self.alive:
            return False
        if self.proc is None:
            h, w = frame.shape[:2]
            try:
                self._start(w, h)
            except Exception as e:
                print(f"[stream] ffmpeg start failed: {e}")
                self.alive = False
                return False
        try:
            if frame.shape[1] != self.stream_width or frame.shape[0] != self.stream_height:
                frame = cv2.resize(frame, (self.stream_width, self.stream_height))
            self.proc.stdin.write(frame.tobytes())
            return True
        except (BrokenPipeError, OSError) as e:
            print(f"[stream] write failed, disabling stream (ffmpeg likely died): {e}")
            self.alive = False
            return False

    def close(self) -> None:
        if self.proc is None:
            return
        try:
            if self.proc.stdin and not self.proc.stdin.closed:
                self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        if self.stderr_file is not None:
            try:
                self.stderr_file.close()
            except Exception:
                pass
