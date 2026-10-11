"""Operating modes. Only one mode is active at a time."""
from __future__ import annotations

import threading
from enum import Enum
from typing import Callable, Optional


class Mode(str, Enum):
    CURSOR = "Cursor Mode"
    SCROLL = "Scroll Mode"
    VOICE = "Voice Mode"
    DICTATION = "Dictation Mode"

    @property
    def short(self) -> str:
        return self.value.replace(" Mode", "")

    @staticmethod
    def from_short(name: str) -> "Mode":
        for m in Mode:
            if m.short.lower() == name.lower():
                return m
        raise ValueError(name)


class ModeManager:
    """Cursor / Scroll / Voice / Dictation.

    * Cursor Mode   - index fingertip moves the pointer, pinch clicks (if enabled).
    * Scroll Mode   - palm centre scrolls; pointer and clicks are paused.
    * Voice Mode    - hand control paused; voice commands only.
    * Dictation Mode- speech is typed; pointer still works so you can pick a text box.
    """

    def __init__(self, on_change: Optional[Callable[[Mode, Mode], None]] = None):
        self._mode = Mode.CURSOR
        self._return_mode = Mode.CURSOR
        self._lock = threading.Lock()
        self.on_change = on_change

    @property
    def mode(self) -> Mode:
        return self._mode

    def set(self, new: Mode) -> bool:
        with self._lock:
            old = self._mode
            if new == old:
                return False
            if new == Mode.DICTATION:
                self._return_mode = old if old != Mode.DICTATION else Mode.CURSOR
            self._mode = new
        if self.on_change:
            self.on_change(old, new)
        return True

    def toggle_scroll(self) -> Mode:
        self.set(Mode.CURSOR if self._mode == Mode.SCROLL else Mode.SCROLL)
        return self._mode

    def leave_dictation(self) -> None:
        if self._mode == Mode.DICTATION:
            self.set(self._return_mode)

    def reset(self) -> None:
        self.set(Mode.CURSOR)

    # what the hand-tracking loop is allowed to do right now
    def cursor_allowed(self) -> bool:
        return self._mode in (Mode.CURSOR, Mode.DICTATION)

    def scroll_allowed(self) -> bool:
        return self._mode == Mode.SCROLL
