"""Global keyboard shortcuts (work even when Handsfree isn't the focused window)."""
from __future__ import annotations

from typing import Callable, Optional


class HotkeyManager:
    def __init__(self, log):
        self.log = log
        self._listener = None

    def start(self, mapping: dict[str, Callable[[], None]]) -> None:
        self.stop()
        try:
            from pynput import keyboard
        except Exception:
            self.log.info("Global shortcuts need 'pynput' (pip install pynput). Window shortcuts still work.")
            return
        valid = {}
        for combo, fn in mapping.items():
            try:
                keyboard.HotKey.parse(combo)
                valid[combo] = fn
            except Exception:
                self.log.warn(f"Shortcut '{combo}' is not valid (example: <f9> or <ctrl>+<alt>+s) - ignored.")
        if not valid:
            return
        try:
            self._listener = keyboard.GlobalHotKeys(valid)
            self._listener.daemon = True
            self._listener.start()
        except Exception as exc:
            self._listener = None
            self.log.warn(f"Global shortcuts unavailable: {exc}")

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
