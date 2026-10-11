"""Colours (light, dark) and fonts shared by every window."""
BG = ("#EEF1F7", "#0E1016")
CARD = ("#FFFFFF", "#181B25")
CARD_ALT = ("#F1F4FA", "#222633")
BORDER = ("#DDE2EC", "#2A2F3D")
TEXT = ("#111827", "#F3F4F6")
MUTED = ("#6B7280", "#9AA3B5")
ACCENT = ("#2563EB", "#4F8CFF")
ACCENT_HOVER = ("#1D4ED8", "#3B79F0")
GOOD = ("#16A34A", "#22C55E")
GOOD_HOVER = ("#15803D", "#16A34A")
WARN = ("#D97706", "#F59E0B")
WARN_HOVER = ("#B45309", "#D97706")
BAD = ("#DC2626", "#EF4444")
BAD_HOVER = ("#B91C1C", "#DC2626")
NEUTRAL = ("#9CA3AF", "#5B6275")
BANNER = ("#FEF3C7", "#3A2E10")

# state -> (colour, label)
STATE_STYLE = {
    "running": (GOOD, "Running"),
    "starting": (ACCENT, "Starting"),
    "paused": (WARN, "Paused"),
    "idle": (ACCENT, "Ready"),
    "off": (NEUTRAL, "Off"),
    "stopped": (NEUTRAL, "Stopped"),
    "error": (BAD, "Error"),
    "waiting": (WARN, "Waiting"),
}
