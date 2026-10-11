"""Scroll Mode: the PALM CENTRE steers scrolling (the index finger is not used).

Hold your hand still where you start = no scroll. Move it up/down past the dead
zone and the page scrolls; the further you move, the faster it goes.
"""
from __future__ import annotations

from typing import Optional

from gestures.poses import dist as _d

PALM_POINTS = (0, 5, 9, 13, 17)
UNITS_PER_SEC = 9000.0
SMOOTH = 0.5              # light smoothing of the hand position so scrolling doesn't stutter


class ScrollController:
    def __init__(self, actions):
        self.actions = actions
        self.reset()

    def reset(self) -> None:
        self._anchor: Optional[float] = None
        self._last_t: Optional[float] = None
        self._acc = 0.0
        self._py: Optional[float] = None

    def hand_lost(self) -> None:
        self.reset()          # re-centre next time the hand appears

    @staticmethod
    def palm_center(lm) -> tuple[float, float]:
        xs = [lm[i].x for i in PALM_POINTS]
        ys = [lm[i].y for i in PALM_POINTS]
        return sum(xs) / len(xs), sum(ys) / len(ys)

    def update(self, lm, now: float, cfg: dict) -> dict:
        px, py = self.palm_center(lm)
        return self.update_point(px, py, now, cfg)

    def update_point(self, px: float, py: float, now: float, cfg: dict) -> dict:
        sc = cfg["scroll"]
        self._py = py if self._py is None else self._py + SMOOTH * (py - self._py)
        py = self._py
        if self._anchor is None:
            self._anchor, self._last_t = py, now
            return {"palm": (px, py), "anchor": py, "scrolling": False}
        dt = min(max(now - (self._last_t or now), 0.0), 0.1)
        self._last_t = now
        offset = self._anchor - py                   # + = hand moved up
        if sc["invert"]:
            offset = -offset
        scrolling = abs(offset) > sc["deadzone"]
        if scrolling:
            rate = (abs(offset) - sc["deadzone"]) * UNITS_PER_SEC * sc["sensitivity"]
            self._acc += (1 if offset > 0 else -1) * rate * dt
            n = int(self._acc)
            if n:
                self.actions.scroll(n)
                self._acc -= n
        else:
            self._acc = 0.0
        return {"palm": (px, py), "anchor": self._anchor, "scrolling": scrolling}


# ---------------------------------------------------------------------------
# Two-finger scroll: raise INDEX + MIDDLE together (ring and little finger down)
# ---------------------------------------------------------------------------
def _extended(lm, tip: int, pip: int) -> bool:
    return _d(lm[0], lm[tip]) > _d(lm[0], lm[pip]) * 1.05


def two_finger_pose(lm) -> bool:
    size = _d(lm[0], lm[9])
    if size < 1e-6:
        return False
    return (_extended(lm, 8, 6) and _extended(lm, 12, 10)
            and not _extended(lm, 16, 14) and not _extended(lm, 20, 18)
            and _d(lm[8], lm[12]) < 0.8 * size)


class TwoFingerScroll:
    """Pose detection with debounce, then scrolls by how far the fingertips move from where you started."""
    ENTER_FRAMES = 3
    EXIT_FRAMES = 5

    def __init__(self, actions):
        self.scroller = ScrollController(actions)
        self.reset()

    def reset(self) -> None:
        self.active = False
        self._on = self._off = 0
        self.scroller.reset()

    def update(self, lm, now: float, cfg: dict) -> tuple[bool, bool, dict]:
        """Returns (active, pose_seen_now, overlay_info)."""
        raw = two_finger_pose(lm)
        if raw:
            self._on, self._off = self._on + 1, 0
        else:
            self._on, self._off = 0, self._off + 1
        if not self.active and self._on >= self.ENTER_FRAMES:
            self.active = True
            self.scroller.reset()
        elif self.active and self._off >= self.EXIT_FRAMES:
            self.active = False
            self.scroller.reset()
        info: dict = {}
        if self.active and raw:
            px = (lm[8].x + lm[12].x) / 2
            py = (lm[8].y + lm[12].y) / 2
            info = self.scroller.update_point(px, py, now, cfg)
            info["two"] = True
        return self.active, raw, info
