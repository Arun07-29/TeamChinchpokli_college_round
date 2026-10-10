"""Configuration manager for Handsfree.

* Holds the default settings (safe: clicking OFF, voice OFF).
* Validates anything loaded from ``config.json`` and falls back to the default
  for every value that is missing, the wrong type, or out of range.
* Saves atomically so a crash can never leave a half-written file.
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
CONFIG_VERSION = 1

LANGUAGES = [
    ("en-US", "English (US)"), ("en-GB", "English (UK)"), ("en-IN", "English (India)"),
    ("hi-IN", "Hindi"), ("es-ES", "Spanish"), ("fr-FR", "French"), ("de-DE", "German"),
    ("it-IT", "Italian"), ("pt-BR", "Portuguese (Brazil)"), ("ja-JP", "Japanese"),
    ("ko-KR", "Korean"), ("zh-CN", "Chinese (Mandarin)"),
]
PINCH_GESTURES = ["off", "thumb_middle", "thumb_ring", "thumb_pinky"]
SEARCH_ENGINES = ["google", "duckduckgo", "bing"]


def _default_apps() -> dict[str, str]:
    """Apps that voice command 'open <name>' is allowed to launch."""
    if os.name == "nt":
        return {
            "notepad": "notepad.exe", "calculator": "calc.exe",
            "file explorer": "explorer.exe", "paint": "mspaint.exe",
            "command prompt": "cmd.exe", "task manager": "taskmgr.exe",
            "settings": "ms-settings:",
        }
    if sys.platform == "darwin":
        return {"notes": "open -a Notes", "calculator": "open -a Calculator",
                "finder": "open -a Finder", "terminal": "open -a Terminal"}
    return {"text editor": "gedit", "calculator": "gnome-calculator", "files": "nautilus"}


DEFAULTS: dict[str, Any] = {
    "version": CONFIG_VERSION,
    "general": {"theme": "dark", "show_preview": True, "auto_start": False},
    "camera": {"index": 0},
    "gestures": {"enabled": True},
    "cursor": {
        "speed": 1.0, "smoothing": 0.70, "steady_px": 2,
        "area": {"left": 0.08, "right": 0.92, "top": 0.08, "bottom": 0.92},
    },
    "click": {
        "enabled": False, "pinch_threshold": 0.045, "cooldown": 0.75,
        "right_click_gesture": "thumb_middle", "double_click_gesture": "thumb_ring",
    },
    "scroll": {"sensitivity": 1.0, "deadzone": 0.04, "invert": False, "two_finger": True},
    "voice": {
        "enabled": False, "microphone": "", "activation": "wake_phrase",
        "wake_phrase": "hey handsfree", "listen_window": 8.0, "energy_threshold": 0,
        "apps": _default_apps(),
    },
    "speech": {"engine": "google", "language": "en-US", "vosk_model": "vosk-model-small-en-us-0.15"},
    "dictation": {"punctuation_commands": True, "auto_capitalize": True, "stop_phrase": "stop dictation"},
    "browser": {
        "enabled": True, "search_engine": "google",
        "home_page": "https://www.google.com", "confirm_risky": True,
    },
    "hotkeys": {"enabled": True, "toggle_scroll": "<f8>", "push_to_talk": "<f9>", "emergency_stop": "<f12>"},
}

# kind, [min, max] or [choices]
RULES: dict[tuple[str, str], tuple] = {
    ("general", "theme"): ("choice", ["dark", "light", "system"]),
    ("general", "show_preview"): ("bool",),
    ("general", "auto_start"): ("bool",),
    ("camera", "index"): ("int", 0, 9),
    ("gestures", "enabled"): ("bool",),
    ("cursor", "speed"): ("float", 0.5, 3.0),
    ("cursor", "smoothing"): ("float", 0.0, 0.95),
    ("cursor", "steady_px"): ("int", 0, 30),
    ("click", "enabled"): ("bool",),
    ("click", "pinch_threshold"): ("float", 0.02, 0.12),
    ("click", "cooldown"): ("float", 0.1, 3.0),
    ("click", "right_click_gesture"): ("choice", PINCH_GESTURES),
    ("click", "double_click_gesture"): ("choice", PINCH_GESTURES),
    ("scroll", "sensitivity"): ("float", 0.2, 3.0),
    ("scroll", "deadzone"): ("float", 0.01, 0.2),
    ("scroll", "invert"): ("bool",),
    ("scroll", "two_finger"): ("bool",),
    ("voice", "enabled"): ("bool",),
    ("voice", "microphone"): ("str", 0, 200),
    ("voice", "activation"): ("choice", ["wake_phrase", "push_to_talk", "always"]),
    ("voice", "wake_phrase"): ("str", 2, 40),
    ("voice", "listen_window"): ("float", 2.0, 30.0),
    ("voice", "energy_threshold"): ("int", 0, 4000),
    ("voice", "apps"): ("apps",),
    ("speech", "engine"): ("choice", ["vosk", "google"]),
    ("speech", "language"): ("choice", [c for c, _ in LANGUAGES]),
    ("speech", "vosk_model"): ("modelname",),
    ("dictation", "punctuation_commands"): ("bool",),
    ("dictation", "auto_capitalize"): ("bool",),
    ("dictation", "stop_phrase"): ("str", 3, 40),
    ("browser", "enabled"): ("bool",),
    ("browser", "search_engine"): ("choice", SEARCH_ENGINES),
    ("browser", "home_page"): ("url",),
    ("browser", "confirm_risky"): ("bool",),
    ("hotkeys", "enabled"): ("bool",),
    ("hotkeys", "toggle_scroll"): ("str", 2, 40),
    ("hotkeys", "push_to_talk"): ("str", 2, 40),
    ("hotkeys", "emergency_stop"): ("str", 2, 40),
}


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check(rule: tuple, value: Any) -> tuple[bool, Any]:
    """Return (is_valid, cleaned_value)."""
    kind = rule[0]
    if kind == "bool":
        return (isinstance(value, bool), value)
    if kind == "int":
        if _num(value) and float(value) == int(value) and rule[1] <= value <= rule[2]:
            return True, int(value)
        return False, None
    if kind == "float":
        if _num(value) and rule[1] <= value <= rule[2]:
            return True, float(value)
        return False, None
    if kind == "choice":
        return (value in rule[1], value)
    if kind == "str":
        if not isinstance(value, str):
            return False, None
        s = value.strip()
        return (True, s) if rule[1] <= len(s) <= rule[2] else (False, None)
    if kind == "modelname":
        ok = isinstance(value, str) and re.fullmatch(r"[\w.\-]{1,100}", value) is not None
        return ok, value
    if kind == "url":
        ok = isinstance(value, str) and re.fullmatch(r"https?://[^\s]{3,300}", value.strip()) is not None
        return ok, value.strip() if ok else None
    if kind == "apps":
        if not isinstance(value, dict):
            return False, None
        clean = {}
        for k, v in value.items():
            if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip() and len(k) <= 50 and len(v) <= 300:
                clean[k.strip().lower()] = v.strip()
        return True, clean
    return False, None


def validate_config(raw: Any) -> tuple[dict, list[str]]:
    """Merge ``raw`` onto the defaults. Invalid values fall back to defaults."""
    warnings: list[str] = []
    out = copy.deepcopy(DEFAULTS)
    if not isinstance(raw, dict):
        return out, ["Config file was not a JSON object - using defaults."]

    for section, defaults in DEFAULTS.items():
        if section == "version":
            continue
        raw_sec = raw.get(section)
        if raw_sec is None:
            continue
        if not isinstance(raw_sec, dict):
            warnings.append(f"Section '{section}' is invalid - defaults used.")
            continue
        for key in defaults:
            if key not in raw_sec:
                continue
            value = raw_sec[key]
            if (section, key) not in RULES:      # e.g. cursor.area handled below
                continue
            ok, clean = _check(RULES[(section, key)], value)
            if ok:
                out[section][key] = clean
            else:
                warnings.append(f"Invalid value for {section}.{key} - default used.")

    # cursor tracking area
    area = (raw.get("cursor") or {}).get("area") if isinstance(raw.get("cursor"), dict) else None
    if area is not None:
        try:
            a = {k: float(area[k]) for k in ("left", "right", "top", "bottom")}
            if all(0.0 <= v <= 1.0 for v in a.values()) and a["right"] - a["left"] >= 0.2 and a["bottom"] - a["top"] >= 0.2:
                out["cursor"]["area"] = a
            else:
                warnings.append("Invalid cursor tracking area - default used.")
        except (KeyError, TypeError, ValueError):
            warnings.append("Invalid cursor tracking area - default used.")

    # right-click and double-click can't share the same finger
    c = out["click"]
    if c["right_click_gesture"] != "off" and c["right_click_gesture"] == c["double_click_gesture"]:
        c["double_click_gesture"] = "off"
        warnings.append("Right-click and double-click used the same gesture - double-click turned off.")
    return out, warnings


class ConfigManager:
    def __init__(self, path: Path | str = CONFIG_PATH):
        self.path = Path(path)
        self.warnings: list[str] = []
        self.config: dict = self.load()

    @staticmethod
    def defaults() -> dict:
        return copy.deepcopy(DEFAULTS)

    @staticmethod
    def validate(raw: Any) -> tuple[dict, list[str]]:
        return validate_config(raw)

    def load(self) -> dict:
        if not self.path.exists():
            cfg = self.defaults()
            self.save(cfg)
            return cfg
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            backup = self.path.with_name(f"config.corrupt-{int(time.time())}.json")
            try:
                self.path.replace(backup)
            except OSError:
                pass
            self.warnings = [f"config.json was unreadable ({exc}); defaults restored, old file kept as {backup.name}."]
            cfg = self.defaults()
            self.save(cfg)
            return cfg
        cfg, self.warnings = validate_config(raw)
        return cfg

    def save(self, cfg: dict) -> bool:
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
            return True
        except OSError as exc:
            self.warnings.append(f"Could not save settings: {exc}")
            return False


def get_path(cfg: dict, dotted: str) -> Any:
    for part in dotted.split("."):
        cfg = cfg[part]
    return cfg


def set_path(cfg: dict, dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    for part in parts[:-1]:
        cfg = cfg[part]
    cfg[parts[-1]] = value
