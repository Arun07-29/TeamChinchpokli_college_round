"""Guided calibration of the hand-tracking area (two corners)."""
from __future__ import annotations

import math
import threading
from typing import Callable, Optional

STEPS = [
    ("top-left", "Move your fingertip to the TOP-LEFT of the area you want to use"),
    ("bottom-right", "Now move your fingertip to the BOTTOM-RIGHT of that area"),
]
COUNTDOWN = 3.0
SAMPLE_TIME = 1.0


class Calibrator:
    def __init__(self, on_done: Callable[[dict], None], on_message: Callable[[str], None]):
        self.on_done = on_done
        self.on_message = on_message      # status/log text
        self._lock = threading.Lock()
        self.active = False
        self.prompt = ""
        self._reset()

    def _reset(self):
        self._step = 0
        self._points: list[tuple[float, float]] = []
        self._phase_start: Optional[float] = None
        self._sample_start: Optional[float] = None
        self._samples: list[tuple[float, float]] = []

    def start(self) -> None:
        with self._lock:
            self._reset()
            self.active = True
            self.prompt = "Get ready - show your hand to the camera"

    def cancel(self) -> None:
        with self._lock:
            self.active = False
            self.prompt = ""
        self.on_message("")

    def update(self, tip: Optional[tuple[float, float]], now: float) -> None:
        finished = None
        with self._lock:
            if not self.active:
                return
            label, text = STEPS[self._step]
            if self._phase_start is None:
                self._phase_start = now
            elapsed = now - self._phase_start
            if elapsed < COUNTDOWN:
                self.prompt = f"{text} - hold still in {math.ceil(COUNTDOWN - elapsed)}"
                self._sample_start, self._samples = None, []
            elif tip is None:
                self.prompt = "I can't see your hand - show it to the camera"
                self._sample_start, self._samples = None, []
            else:
                if self._sample_start is None:
                    self._sample_start = now
                self._samples.append(tip)
                self.prompt = f"Hold still... capturing {label}"
                if now - self._sample_start >= SAMPLE_TIME and len(self._samples) >= 5:
                    xs, ys = zip(*self._samples)
                    self._points.append((sum(xs) / len(xs), sum(ys) / len(ys)))
                    self._step += 1
                    self._phase_start = None
                    self._sample_start, self._samples = None, []
                    if self._step >= len(STEPS):
                        finished = list(self._points)
                        self.active = False
                        self.prompt = ""
        self.on_message(self.prompt)
        if finished:
            (x1, y1), (x2, y2) = finished
            area = {"left": round(min(x1, x2), 3), "right": round(max(x1, x2), 3),
                    "top": round(min(y1, y2), 3), "bottom": round(max(y1, y2), 3)}
            if area["right"] - area["left"] < 0.2 or area["bottom"] - area["top"] < 0.2:
                self.on_message("")
                self.on_done({})           # empty = failed (too small)
            else:
                self.on_done(area)
