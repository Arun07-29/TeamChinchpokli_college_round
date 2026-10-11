"""Ask-before-doing for risky actions. Works by voice ("yes"/"no") or on-screen buttons."""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from core.status import ActivityLog


class ConfirmationManager:
    def __init__(self, log: ActivityLog, timeout: float = 12.0):
        self.log = log
        self.timeout = timeout
        self._lock = threading.Lock()
        self._pending: Optional[tuple[str, Callable[[], None], float]] = None

    def request(self, prompt: str, on_yes: Callable[[], None]) -> None:
        with self._lock:
            self._pending = (prompt, on_yes, time.time() + self.timeout)
        self.log.warn(f"Confirm needed: {prompt}  (say 'yes' or 'no')")

    def current(self) -> Optional[tuple[str, float]]:
        """(prompt, seconds_left) or None. Expires old requests."""
        with self._lock:
            if not self._pending:
                return None
            prompt, _, deadline = self._pending
            left = deadline - time.time()
            if left <= 0:
                self._pending = None
                expired = True
            else:
                expired = False
        if expired:
            self.log.info("Confirmation timed out - action cancelled.")
            return None
        return prompt, left

    def has_pending(self) -> bool:
        return self.current() is not None

    def resolve(self, yes: bool) -> None:
        with self._lock:
            pending, self._pending = self._pending, None
        if not pending:
            return
        prompt, on_yes, _ = pending
        if yes:
            try:
                on_yes()
            except Exception as exc:   # never crash the caller
                self.log.error(f"Action failed: {exc}")
        else:
            self.log.info(f"Cancelled: {prompt}")

    def cancel(self) -> None:
        with self._lock:
            self._pending = None
