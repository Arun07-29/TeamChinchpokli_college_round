"""Thread-safe live status board and activity log shared by every module."""
from __future__ import annotations

import logging
import threading
import time
from collections import deque

FEATURES = [
    ("webcam", "Webcam"),
    ("hand_tracking", "Hand tracking"),
    ("cursor", "Cursor"),
    ("scrolling", "Scrolling"),
    ("voice", "Voice control"),
    ("microphone", "Microphone"),
    ("dictation", "Dictation"),
    ("browser", "Browser control"),
]
# running | starting | paused | idle | off | stopped | error | waiting


class StatusBoard:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = {key: ("stopped", "") for key, _ in FEATURES}
        self.info = {"last_heard": "", "last_action": "", "calibration": "", "partial": "", "mic_level": 0.0}

    def set(self, key: str, state: str, detail: str = "") -> None:
        with self._lock:
            self._data[key] = (state, detail)

    def set_info(self, key: str, value: str) -> None:
        with self._lock:
            self.info[key] = value

    def snapshot(self) -> dict:
        with self._lock:
            return {"features": dict(self._data), "info": dict(self.info)}


class ActivityLog:
    def __init__(self, maxlen: int = 400):
        self._lock = threading.Lock()
        self._items: deque = deque(maxlen=maxlen)
        self._counter = 0
        self._logger = logging.getLogger("handsfree")

    def add(self, level: str, text: str) -> None:
        with self._lock:
            self._counter += 1
            self._items.append((self._counter, time.strftime("%H:%M:%S"), level, text))
        getattr(self._logger, {"error": "error", "warn": "warning"}.get(level, "info"))(text)

    def info(self, text: str) -> None: self.add("info", text)
    def warn(self, text: str) -> None: self.add("warn", text)
    def error(self, text: str) -> None: self.add("error", text)

    def since(self, last_id: int) -> list[tuple]:
        with self._lock:
            return [i for i in self._items if i[0] > last_id]
