"""All mouse/keyboard output goes through here (one lock, one failsafe handler)."""
from __future__ import annotations

import sys
import threading
import time
from typing import Callable, Optional

from core.status import ActivityLog

try:                                     # may fail on a machine with no display
    import pyautogui
    pyautogui.FAILSAFE = True            # slam the mouse into the top-left corner to stop
    pyautogui.PAUSE = 0.01
    _PYAUTOGUI_ERROR = None
except Exception as exc:                  # pragma: no cover
    pyautogui = None
    _PYAUTOGUI_ERROR = str(exc)

try:
    import pyperclip
except Exception:                         # optional
    pyperclip = None

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")
MOD = "command" if IS_MAC else "ctrl"
NOTCH = 120 if IS_WIN else 5              # one wheel "click"

_user32 = None
if IS_WIN and pyautogui is not None:      # direct cursor moves: ~100x faster than pyautogui.moveTo
    try:
        import ctypes
        _user32 = ctypes.windll.user32
    except Exception:                     # pragma: no cover
        _user32 = None


class InputActions:
    def __init__(self, log: ActivityLog, on_failsafe: Optional[Callable[[], None]] = None):
        self.log = log
        self.on_failsafe = on_failsafe
        self._lock = threading.RLock()
        self._button_down = False

    @property
    def available(self) -> bool:
        return pyautogui is not None

    @property
    def error(self) -> Optional[str]:
        return _PYAUTOGUI_ERROR

    def screen_size(self) -> tuple[int, int]:
        return tuple(pyautogui.size()) if pyautogui else (1920, 1080)

    def position(self) -> tuple[int, int]:
        return tuple(pyautogui.position()) if pyautogui else (0, 0)

    def _run(self, fn):
        if pyautogui is None:
            return
        with self._lock:
            try:
                return fn()
            except pyautogui.FailSafeException:
                if self.on_failsafe:
                    self.on_failsafe()

    def move(self, x: int, y: int) -> None:
        if _user32 is None:
            self._run(lambda: pyautogui.moveTo(int(x), int(y), _pause=False))
            return
        with self._lock:
            # keep PyAutoGUI's safety net: a real mouse slammed into a corner still stops everything
            if pyautogui.FAILSAFE and tuple(pyautogui.position()) in pyautogui.FAILSAFE_POINTS:
                if self.on_failsafe:
                    self.on_failsafe()
                return
            _user32.SetCursorPos(int(x), int(y))

    def move_rel(self, dx: int, dy: int) -> None:
        x, y = self.position()
        w, h = self.screen_size()
        self.move(min(max(x + dx, 1), w - 2), min(max(y + dy, 1), h - 2))

    def click(self) -> None: self._run(lambda: pyautogui.click())
    def right_click(self) -> None: self._run(lambda: pyautogui.rightClick())
    def middle_click(self) -> None: self._run(lambda: pyautogui.middleClick())
    def double_click(self) -> None: self._run(lambda: pyautogui.doubleClick())

    def mouse_down(self) -> None:
        self._button_down = True
        self._run(lambda: pyautogui.mouseDown(_pause=False))

    def mouse_up(self) -> None:
        self._button_down = False
        self._run(lambda: pyautogui.mouseUp(_pause=False))

    def release_all(self) -> None:
        """Let go of a held mouse button (used by stop / emergency stop)."""
        if self._button_down:
            self.mouse_up()

    def scroll(self, units: int) -> None:
        if units:
            self._run(lambda: pyautogui.scroll(int(units), _pause=False))

    def hscroll(self, units: int) -> None:
        if units:
            self._run(lambda: pyautogui.hscroll(int(units), _pause=False))

    def scroll_notches(self, n: int) -> None: self.scroll(n * NOTCH)
    def hscroll_notches(self, n: int) -> None: self.hscroll(n * NOTCH)
    def press(self, key: str, presses: int = 1) -> None: self._run(lambda: pyautogui.press(key, presses=presses, interval=0.03))
    def hotkey(self, *keys: str) -> None: self._run(lambda: pyautogui.hotkey(*keys))

    def type_text(self, text: str) -> None:
        """Type into whatever has focus. Uses the clipboard when possible (handles any language)."""
        if not text:
            return
        def _do():
            if pyperclip is not None:
                try:
                    old = pyperclip.paste()
                except Exception:
                    old = None
                try:
                    pyperclip.copy(text)
                    pyautogui.hotkey(MOD, "v")
                    time.sleep(0.15)
                finally:
                    if old is not None:
                        try:
                            pyperclip.copy(old)
                        except Exception:
                            pass
            else:
                pyautogui.write(text, interval=0.004)     # ASCII only
        self._run(_do)
