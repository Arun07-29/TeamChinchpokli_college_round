"""Smooth pointer: the webcam only delivers 30 frames per second, so moving the mouse once per frame
looks steppy. This thread glides the real pointer toward the latest target ~120 times a second,
so the pointer moves as smoothly as a 120 fps camera would (adds only ~15 ms of delay)."""
from __future__ import annotations

import math
import threading
import time
from typing import Optional

RATE_HZ = 120
TAU = 0.016          # seconds; ~85% of each 30 fps step is covered before the next camera frame


class PointerGlide:
    def __init__(self, actions):
        self.actions = actions
        self._lock = threading.Lock()
        self._target: Optional[tuple[float, float]] = None
        self._pos: Optional[tuple[float, float]] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.moves_per_sec = 0.0

    # ---- lifecycle -------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="pointer-glide", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t and t is not threading.current_thread():
            t.join(1.0)
        self.halt()

    # ---- control -----------------------------------------------------------
    def target(self, x: int, y: int) -> None:
        """Glide toward (x, y). Starts from the real pointer position after a pause."""
        with self._lock:
            if self._pos is None:
                px, py = self.actions.position()
                self._pos = (float(px), float(py))
            self._target = (float(x), float(y))

    def snap(self, x: int, y: int) -> None:
        """Jump straight to (x, y) - used for clicks, which must land exactly."""
        with self._lock:
            self._target = self._pos = (float(x), float(y))
        self.actions.move(int(x), int(y))

    def halt(self) -> None:
        """Stop where we are (hand lost / paused)."""
        with self._lock:
            self._target = self._pos = None

    # ---- loop ----------------------------------------------------------------
    def _run(self) -> None:
        period = 1.0 / RATE_HZ
        last = time.perf_counter()
        count, count_t = 0, last
        while not self._stop.is_set():
            time.sleep(period)                      # high-resolution timer on Python 3.11+ (Windows)
            now = time.perf_counter()
            dt, last = now - last, now
            with self._lock:
                tgt, pos = self._target, self._pos
                if tgt is None or pos is None:
                    continue
                dx, dy = tgt[0] - pos[0], tgt[1] - pos[1]
                if abs(dx) < 0.5 and abs(dy) < 0.5:
                    continue
                a = 1.0 - math.exp(-dt / TAU)
                pos = tgt if math.hypot(dx, dy) * (1 - a) < 1.0 else (pos[0] + dx * a, pos[1] + dy * a)
                self._pos = pos
            self.actions.move(int(round(pos[0])), int(round(pos[1])))
            count += 1
            if now - count_t >= 1.0:
                self.moves_per_sec, count, count_t = count / (now - count_t), 0, now
