"""Local frame storage. Saves original (unannotated) frame."""

from pathlib import Path

import cv2


def save_frame(frame, output_dir: Path, event_id: str) -> str:
    event_dir = output_dir / "events" / event_id
    event_dir.mkdir(parents=True, exist_ok=True)
    file_path = event_dir / "thumb.jpg"
    cv2.imwrite(str(file_path), frame)
    return f"events/{event_id}/thumb.jpg"
