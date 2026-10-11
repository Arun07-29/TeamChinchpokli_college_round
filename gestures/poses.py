"""Hand-pose maths shared by the gesture controllers (pure functions - easy to test).

MediaPipe landmark ids: 0 wrist, 4 thumb tip, 5/9/13/17 knuckles (MCP),
6/10/14/18 middle joints (PIP), 8/12/16/20 fingertips.
"""
from __future__ import annotations

import math

TIPS = {"index": 8, "middle": 12, "ring": 16, "pinky": 20}
PIPS = {"index": 6, "middle": 10, "ring": 14, "pinky": 18}
ASPECT = 1.0      # camera width / height; set by the gesture engine so x and y use the same units


def dist(a, b) -> float:
    """3-D distance in image-height units (z is MediaPipe's relative depth, scaled like x;
    0 for fake test landmarks)."""
    return math.sqrt(((a.x - b.x) * ASPECT) ** 2 + (a.y - b.y) ** 2
                     + ((getattr(a, "z", 0.0) - getattr(b, "z", 0.0)) * ASPECT) ** 2)


def palm_size(lm) -> float:
    """Hand scale that barely changes when the hand turns or moves nearer/further from the camera."""
    return max(dist(lm[0], lm[9]), dist(lm[0], lm[5]), dist(lm[5], lm[17]) * 1.2, 1e-6)


def pinch_ratios(lm) -> dict[str, float]:
    """Thumb-tip to each fingertip distance, divided by palm size (so it works near or far)."""
    size = palm_size(lm)
    return {name: dist(lm[4], lm[i]) / size for name, i in TIPS.items()}


def curled(lm, finger: str) -> bool:
    """Fingertip is closer to the wrist than its middle joint = finger folded into the palm."""
    return dist(lm[0], lm[TIPS[finger]]) < dist(lm[0], lm[PIPS[finger]])


def is_fist(lm) -> bool:
    return all(curled(lm, f) for f in TIPS)


class OneEuroFilter:
    """Adaptive low-pass filter (Casiez et al. 2012): heavy smoothing when the hand is still
    (no jitter), almost none when it moves fast (no lag)."""

    def __init__(self, min_cutoff: float = 1.0, beta: float = 10.0, d_cutoff: float = 1.0):
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self.reset()

    def reset(self) -> None:
        self._x = self._dx = self._t = None

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x: float, t: float) -> float:
        if self._x is None or self._t is None:
            self._x, self._dx, self._t = x, 0.0, t
            return x
        dt = min(max(t - self._t, 1e-3), 0.2)
        self._t = t
        dx = (x - self._x) / dt
        self._dx += self._alpha(self.d_cutoff, dt) * (dx - self._dx)
        cutoff = self.min_cutoff + self.beta * abs(self._dx)
        self._x += self._alpha(cutoff, dt) * (x - self._x)
        return self._x


def smoothing_to_cutoff(smoothing: float) -> float:
    """Map the 0-95% 'Smoothing' slider to a One-Euro minimum cutoff (5 Hz snappy .. 0.4 Hz steady)."""
    f = min(max(smoothing / 0.95, 0.0), 1.0)
    return 10 ** (math.log10(5.0) + f * (math.log10(0.4) - math.log10(5.0)))
