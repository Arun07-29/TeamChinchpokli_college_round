"""Tiny non-blocking sound cues so you know you were heard without looking at the screen."""
from __future__ import annotations

import sys
import threading

TONES = {
    "wake": ((880, 70), (1175, 70)),      # listening for a command
    "done": ((1320, 60),),                # command carried out
    "error": ((330, 140),),               # didn't understand / couldn't do it
}


def play(kind: str) -> None:
    if not sys.platform.startswith("win") or kind not in TONES:
        return

    def _beep():
        try:
            import winsound
            for freq, ms in TONES[kind]:
                winsound.Beep(freq, ms)
        except Exception:
            pass
    threading.Thread(target=_beep, name="sound", daemon=True).start()
