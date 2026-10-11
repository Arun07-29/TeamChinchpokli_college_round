"""Webcam helpers."""
from __future__ import annotations

import os
import sys

# Media Foundation opens much faster without hardware transforms (must be set before cv2 loads)
os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")


def _backends():
    import cv2
    if sys.platform.startswith("win"):
        # Media Foundation first: many laptop webcams give 30 fps there but only ~10 fps through
        # DirectShow in normal indoor light (DirectShow lets auto-exposure slow the frame rate).
        return [cv2.CAP_MSMF, cv2.CAP_DSHOW]
    return [cv2.CAP_ANY]


def _configure(cap, width: int, height: int) -> None:
    import cv2
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)              # always hand us the newest frame (low delay)


RESOLUTIONS = {"720p": (1280, 720), "480p": (640, 480)}


def open_camera(index: int, width: int = 1280, height: int = 720, probe: bool = True):
    """Open a camera tuned for low delay, or return None if it can't be opened."""
    import cv2
    for backend in _backends():
        cap = cv2.VideoCapture(index, backend)
        if not cap.isOpened():
            cap.release()
            continue
        _configure(cap, width, height)
        if not probe:
            return cap
        for _ in range(10):                          # some cameras need a few frames to wake up
            ok, _frame = cap.read()
            if ok:
                return cap
        cap.release()                                # opened but no video -> try the next backend
    return None


def list_cameras(max_index: int = 5, skip: tuple[int, ...] = ()) -> list[int]:
    """Indexes that respond. Indexes in ``skip`` (already in use) are assumed present."""
    found = []
    for i in range(max_index + 1):
        if i in skip:
            found.append(i)
            continue
        cap = open_camera(i, probe=False)
        if cap is not None:
            found.append(i)
            cap.release()
    return found
