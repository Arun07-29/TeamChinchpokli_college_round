"""Index-fingertip cursor + pinch gestures.

* Pointer: One-Euro filtered fingertip -> steady when still, no lag when moving fast.
* Pinch thumb + index: mouse button DOWN on pinch, UP on release (a quick pinch = click).
  Keep pinching for ``hold_time`` (or move your hand) and you are dragging.
* Pinch thumb + middle / ring / little finger: right-click / double-click (configurable).
* Pinches are measured relative to hand size, need 2 frames to register and must open
  wider than they closed to release (hysteresis) - so no flicker double-clicks.
* The click lands where the pointer was just BEFORE your fingers closed (no pinch drift).
* Fist = hold the pointer still (rest your hand without moving the mouse).
* Optional dwell click: hold the pointer still for ``dwell_time`` to click.
"""
from __future__ import annotations

import math
from collections import deque
from typing import Optional

from gestures.poses import TIPS, OneEuroFilter, is_fist, pinch_ratios, smoothing_to_cutoff

FINGER_TIPS = TIPS
GESTURE_FINGER = {"thumb_middle": "middle", "thumb_ring": "ring", "thumb_pinky": "pinky"}

PRESS_FRAMES = 2          # frames a pinch must be seen before it counts
RELEASE_FACTOR = 1.4      # fingers must open to thr * this to release
FIST_FRAMES = 4
SNAP_BACK = 0.12          # seconds: click where the pointer was before the pinch closed
DRAG_MOVE_PX = 35         # moving this far while pinched starts a drag straight away
DWELL_RADIUS_PX = 25
FILTER_BETA = 8.0


class CursorController:
    def __init__(self, actions, glide=None):
        self.actions = actions
        self.glide = glide                  # optional PointerGlide: smooth 120 Hz pointer
        self._use_glide = False
        self.fx = OneEuroFilter(beta=FILTER_BETA)
        self.fy = OneEuroFilter(beta=FILTER_BETA)
        self._dragging = False
        self._last_click = -1e9
        self.reset()

    # ---- state -------------------------------------------------------
    def reset(self) -> None:
        """Forget everything (mode change / start). Releases a held mouse button."""
        self.hand_lost()
        self._last_click = -1e9
        self._last_sent = (-1, -1)

    def release(self) -> None:
        if self._dragging:
            self.actions.mouse_up()
        self._dragging = False
        self._drag_live = False

    def hand_lost(self) -> None:
        self.release()
        self._held: Optional[str] = None        # finger currently pinching the thumb
        self._candidate: Optional[str] = None
        self._cand_frames = 0
        self._freeze_at: Optional[tuple[int, int]] = None
        self._press_pos = (0, 0)
        self._press_t = 0.0
        self._drag_offset = (0, 0)
        self._fist_frames = 0
        self.fist = False
        self._history: deque = deque()
        self._dwell_anchor: Optional[tuple[int, int]] = None
        self._dwell_t = 0.0
        self._dwell_done = False
        self.fx.reset()
        self.fy.reset()
        if self.glide is not None:
            self.glide.halt()

    def suspend(self) -> None:
        """Pointer is being ignored (e.g. two-finger scroll)."""
        self.hand_lost()

    @property
    def dragging(self) -> bool:
        return self._dragging

    # ---- per frame ---------------------------------------------------
    def update(self, lm, now: float, cfg: dict) -> dict:
        """Process one frame. Returns info used for the preview overlay."""
        cur, click = cfg["cursor"], cfg["click"]
        self._use_glide = self.glide is not None and cur.get("glide", True)
        thr = click["pinch_ratio"]
        ratios = pinch_ratios(lm)
        closest = min(ratios, key=ratios.get)
        info = {"ratio": ratios["index"], "thr": thr, "active": None}

        # fist = hold the pointer still
        fist_pose = is_fist(lm)                 # a closing fist must never count as a pinch
        fist_raw = cfg["gestures"].get("fist_freeze", True) and fist_pose
        self._fist_frames = self._fist_frames + 1 if fist_raw else 0
        if self.fist and not fist_raw:
            self.fist = False
            self.fx.reset(); self.fy.reset()
            # fingers uncurling past the thumb must not click: wait until they open
            self._held = closest if ratios[closest] < thr * RELEASE_FACTOR else None
        elif not self.fist and self._fist_frames >= FIST_FRAMES:
            self.fist = True
            self.release()
            self._held, self._candidate, self._cand_frames, self._freeze_at = None, None, 0, None
        if self.fist:
            info["fist"] = True
            return info

        x, y = self._target(lm[8], now, cur)
        self._history.append((now, x, y))
        while self._history and now - self._history[0][0] > 0.5:
            self._history.popleft()

        # pinch state machine
        if self._held is not None:
            if ratios[self._held] > thr * RELEASE_FACTOR:
                self.release()
                self._held, self._freeze_at = None, None
        elif ratios[closest] < thr and not fist_pose:
            if self._candidate == closest:
                self._cand_frames += 1
            else:
                self._candidate, self._cand_frames = closest, 1
            if self._cand_frames >= PRESS_FRAMES:
                self._held, self._candidate, self._cand_frames = closest, None, 0
                self._on_press(closest, now, (x, y), click)
        else:
            self._candidate, self._cand_frames = None, 0

        # move (frozen while pinching, unless dragging)
        if self._dragging and not self._drag_live:
            moved = math.hypot(x - self._press_pos[0], y - self._press_pos[1])
            if now - self._press_t >= click["hold_time"] or moved > DRAG_MOVE_PX:
                self._drag_live = True
                self._drag_offset = (self._freeze_at[0] - self._press_pos[0], self._freeze_at[1] - self._press_pos[1])
        if self._freeze_at is None:
            self._send(x, y)
        elif self._drag_live:
            self._send(x + self._drag_offset[0], y + self._drag_offset[1])

        info["dwell"] = self._dwell(now, click)
        if click["enabled"] and self._held is not None:
            info["active"] = self._held
        info["drag"] = self._dragging
        return info

    def _on_press(self, finger: str, now: float, pos: tuple[int, int], click: dict) -> None:
        if not click["enabled"] or now - self._last_click < click["cooldown"]:
            return
        self._last_click = now
        self._freeze_at = self._position_before(now - SNAP_BACK)
        self._press_pos, self._press_t = pos, now
        a = self.actions
        if self._use_glide:
            self.glide.snap(*self._freeze_at)
        else:
            a.move(*self._freeze_at)
        self._last_sent = self._freeze_at
        if finger == "index":
            if click["drag_enabled"]:
                a.mouse_down()
                self._dragging, self._drag_live = True, False
            else:
                a.click()
        elif GESTURE_FINGER.get(click["right_click_gesture"]) == finger:
            a.right_click()
        elif GESTURE_FINGER.get(click["double_click_gesture"]) == finger:
            a.double_click()

    def _dwell(self, now: float, click: dict) -> float:
        """Dwell click. Returns progress 0..1 for the overlay."""
        if not (click["enabled"] and click.get("dwell_enabled")) or self._held is not None or self._last_sent[0] < 0:
            self._dwell_anchor = None
            return 0.0
        pos = self._last_sent
        if self._dwell_anchor is None or math.hypot(pos[0] - self._dwell_anchor[0], pos[1] - self._dwell_anchor[1]) > DWELL_RADIUS_PX:
            self._dwell_anchor, self._dwell_t, self._dwell_done = pos, now, False
            return 0.0
        if self._dwell_done:
            return 0.0
        progress = (now - self._dwell_t) / click["dwell_time"]
        if progress >= 1.0:
            self.actions.click()
            self._dwell_done = True
            self._last_click = now
            return 0.0
        return progress

    # ---- geometry ----------------------------------------------------
    def _target(self, tip, now: float, cur: dict) -> tuple[int, int]:
        a = cur["area"]
        u = (tip.x - a["left"]) / (a["right"] - a["left"])
        v = (tip.y - a["top"]) / (a["bottom"] - a["top"])
        gain = cur["speed"]
        u = 0.5 + (u - 0.5) * gain
        v = 0.5 + (v - 0.5) * gain
        cutoff = smoothing_to_cutoff(cur["smoothing"])
        self.fx.min_cutoff = self.fy.min_cutoff = cutoff
        u = min(1.0, max(0.0, self.fx(u, now)))
        v = min(1.0, max(0.0, self.fy(v, now)))
        sw, sh = self.actions.screen_size()
        # stay 1 px inside the screen: the exact corners trigger PyAutoGUI's emergency failsafe
        x = int(min(max(round(u * (sw - 1)), 1), sw - 2))
        y = int(min(max(round(v * (sh - 1)), 1), sh - 2))
        self._steady_px = cur["steady_px"]
        return x, y

    def _position_before(self, t: float) -> tuple[int, int]:
        best = None
        for ts, x, y in self._history:
            if ts <= t:
                best = (x, y)
            else:
                break
        if best is None:
            best = (self._history[0][1], self._history[0][2]) if self._history else self._last_sent
        return best

    def _send(self, x: int, y: int) -> None:
        if math.hypot(x - self._last_sent[0], y - self._last_sent[1]) >= self._steady_px:
            if self._use_glide:
                self.glide.target(x, y)
            else:
                self.actions.move(x, y)
            self._last_sent = (x, y)
