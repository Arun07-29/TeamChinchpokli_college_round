"""Turn recognised speech into a Command. Pure functions - easy to test."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

TLDS = {"com", "org", "net", "in", "io", "edu", "gov", "co", "uk"}
NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
           "eight": 8, "nine": 9, "ten": 10}
KEYS = {"enter", "escape", "tab", "space", "backspace", "delete", "up", "down", "left", "right",
        "home", "end", "page up", "page down"}
KEY_NAME = {"page up": "pageup", "page down": "pagedown"}
BROWSER_WORDS = {"browser", "web browser", "the browser", "internet"}
YES = {"yes", "yeah", "confirm", "do it", "okay", "ok", "sure", "proceed"}
NO = {"no", "nope", "cancel", "never mind", "stop", "dont", "don't"}
EMERGENCY = {"emergency stop", "stop everything", "emergency"}


@dataclass
class Command:
    name: str
    args: dict = field(default_factory=dict)


def normalize(text: str) -> str:
    t = text.lower().replace("'", "'")
    t = re.sub(r"[^a-z0-9' ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"^(please )+", "", t)
    t = re.sub(r"( please)+$", "", t)
    return t


FILLERS = {"a", "uh", "um", "ok", "okay", "so", "and", "oh"}


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def strip_wake_phrase(t: str, wake: str, threshold: float = 0.78) -> str | None:
    """If ``t`` starts with the wake phrase return the rest ('' if nothing follows), else None.

    Forgiving on purpose: spaces are ignored ('hey hands free' = 'hey handsfree'), a stray leading
    filler word is skipped, and near-misses from the recogniser ('hey hans free') still match."""
    from difflib import SequenceMatcher
    target = _squash(wake)
    if not target:
        return None
    words = t.split()
    start = 1 if words and words[0] in FILLERS and _squash(words[0]) != target[:len(words[0])] else 0
    best = None                                   # (score, end_index)
    joined = ""
    for i in range(start, min(len(words), start + 5)):
        joined += _squash(words[i])
        if len(joined) > len(target) + 3:
            break
        score = SequenceMatcher(None, joined, target).ratio()
        if score >= threshold and (best is None or score > best[0] + 1e-9):
            best = (score, i)
    if best is None:
        return None
    return " ".join(words[best[1] + 1:])


def normalize_site(spoken: str) -> str:
    """'youtube dot com' / 'youtube com' -> 'youtube.com'. Returns '' if it isn't a clear site."""
    words = spoken.split()
    words = ["." if w == "dot" else w for w in words]
    if len(words) >= 2 and words[-1] in TLDS and "." not in words:
        words = words[:-1] + ["."] + [words[-1]]
    site = "".join(words)
    return site if re.fullmatch(r"[a-z0-9\-]+(\.[a-z0-9\-]+)+(/[^\s]*)?", site) else ""


_EXACT: dict[str, tuple] = {}


def _add(names, cmd, **args):
    for n in names.split("|"):
        _EXACT[n] = (cmd, args)


_add("click|left click|select|tap", "click")
_add("double click|double tap", "double_click")
_add("right click|context menu", "right_click")
_add("pause|pause handsfree", "pause")
_add("resume|resume handsfree|continue", "resume")
_add("cursor mode|mouse mode", "mode", mode="Cursor")
_add("scroll mode", "mode", mode="Scroll")
_add("voice mode", "mode", mode="Voice")
_add("start dictation|dictation|dictate|start dictating|dictation mode", "dictation_start")
_add("enable clicking|turn on clicking|enable click", "set_click", on=True)
_add("disable clicking|turn off clicking|disable click", "set_click", on=False)
_add("page up", "key", key="pageup")
_add("page down", "key", key="pagedown")
_add("scroll to top|go to top|top of page", "key", key="home")
_add("scroll to bottom|go to bottom|bottom of page", "key", key="end")
_add("go back|navigate back", "browser", action="back")
_add("go forward|navigate forward", "browser", action="forward")
_add("refresh|refresh page|reload|reload page", "browser", action="refresh")
_add("new tab|open new tab", "browser", action="new_tab")
_add("close tab|close this tab", "browser", action="close_tab")
_add("next tab|switch tab", "browser", action="next_tab")
_add("previous tab|last tab", "browser", action="prev_tab")
_add("close window", "browser", action="close_window")
_add("address bar|focus address bar", "browser", action="address_bar")
_add("zoom in", "browser", action="zoom_in")
_add("zoom out", "browser", action="zoom_out")
_add("reset zoom", "browser", action="zoom_reset")
_add("home page|go home", "browser", action="home")
_add("open browser|launch browser|open web browser", "browser", action="open")
_add("switch window", "system", action="switch_window")
_add("show desktop", "system", action="show_desktop")
_add("help|what can i say", "help")


def parse_command(t: str, apps: dict | None = None) -> Command | None:
    """``t`` must already be normalised."""
    if not t:
        return None
    if t in _EXACT:
        name, args = _EXACT[t]
        return Command(name, dict(args))

    m = re.fullmatch(r"scroll (up|down)(?: (\w+))?", t)
    if m:
        n = NUMBERS.get(m.group(2) or "", None)
        if n is None and m.group(2) and m.group(2).isdigit():
            n = int(m.group(2))
        if m.group(2) and n is None:
            return None
        return Command("scroll", {"direction": m.group(1), "notches": min(n or 3, 20)})

    m = re.fullmatch(r"press (.+)", t)
    if m and m.group(1) in KEYS:
        k = m.group(1)
        return Command("key", {"key": KEY_NAME.get(k, k)})

    m = re.fullmatch(r"(?:go to|navigate to|visit) (.+)", t)
    if m:
        return Command("browser", {"action": "go_to", "target": m.group(1)})

    m = re.fullmatch(r"(?:search for|search|google) (.+)", t)
    if m:
        return Command("browser", {"action": "search", "query": m.group(1)})

    m = re.fullmatch(r"type (.+)", t)
    if m:
        return Command("type", {"text": m.group(1)})

    m = re.fullmatch(r"(?:open|launch|start) (.+)", t)
    if m:
        name = m.group(1)
        if name in BROWSER_WORDS:
            return Command("browser", {"action": "open"})
        return Command("open_app", {"name": name})
    return None


HELP_TEXT = (
    "Mouse:  click · double click · right click · scroll up / down [number] · page up / down\n"
    "Modes:  cursor mode · scroll mode · voice mode · start dictation · pause · resume\n"
    "Keys:   press enter / escape / tab / space / backspace / delete · type <words>\n"
    "Browser: go back · go forward · refresh · new tab · close tab · next tab · previous tab\n"
    "        go to <site> · search for <words> · open browser · zoom in / out\n"
    "Apps:   open <name>  (only apps listed in Settings > Voice)\n"
    "System: switch window · show desktop · enable clicking · disable clicking\n"
    "Safety: say 'emergency stop' any time. Risky actions ask you to say 'yes' or 'no'."
)
