"""AppController: the one place that starts/stops/pauses every module and applies settings."""
from __future__ import annotations

import copy
import threading
from typing import Optional

from browser.browser_controller import BrowserController
from config_manager import ConfigManager, get_path, set_path
from core.actions import InputActions
from core.confirmation import ConfirmationManager
from core.hotkeys import HotkeyManager
from core.mode_manager import Mode, ModeManager
from core.status import ActivityLog, StatusBoard
from gestures.calibration import Calibrator
from gestures.gesture_engine import GestureEngine
from voice.model_manager import LANG_MODELS, download_model
from voice.session import VoiceSession
from voice.speech_engine import SpeechEngine


class AppController:
    def __init__(self, config: ConfigManager):
        self.cm = config
        self.cfg: dict = config.config
        self.state = "stopped"            # stopped | running | paused
        self.stopping = False
        self.last_stop_reason = ""
        self._lock = threading.RLock()

        self.status = StatusBoard()
        self.log = ActivityLog()
        for w in config.warnings:
            self.log.warn(w)
        self.modes = ModeManager(on_change=self._on_mode_change)
        self.confirm = ConfirmationManager(self.log)
        self.actions = InputActions(self.log, on_failsafe=lambda: self.emergency_stop("Failsafe - mouse moved to top-left corner"))
        self.calibrator = Calibrator(self._on_calibration_done, lambda msg: self.status.set_info("calibration", msg))
        self.browser = BrowserController(self.actions, self.status, self.log, lambda: self.cfg)
        self.gestures = GestureEngine(lambda: self.cfg, self.actions, self.modes, self.status, self.log,
                                      lambda: self.state == "paused", self.calibrator,
                                      on_fatal=lambda m: None)
        self.session = VoiceSession(self)
        self.speech = SpeechEngine(lambda: self.cfg, self.status, self.log, self.session.handle_text)
        self.hotkeys = HotkeyManager(self.log)
        self.model_download = {"active": False, "progress": 0.0, "message": "", "done_name": ""}
        self._refresh_idle_status()
        if not self.actions.available:
            self.log.error(f"Mouse/keyboard control unavailable: {self.actions.error}")

    # ------------------------------------------------------------ status
    def _refresh_idle_status(self) -> None:
        s = self.status
        s.set("webcam", "stopped"); s.set("hand_tracking", "stopped")
        s.set("cursor", "stopped"); s.set("scrolling", "stopped")
        s.set("voice", "stopped"); s.set("microphone", "stopped")
        s.set("browser", "stopped"); s.set("dictation", "idle" if self.speech.running else "stopped")
        self._sync_disabled_status()

    def _sync_disabled_status(self) -> None:
        """Show 'Off' for features that are switched off in settings."""
        cfg, s = self.cfg, self.status
        snap = s.snapshot()["features"]
        def off(key, enabled):
            if not enabled and snap[key][0] in ("stopped", "idle", "off"):
                s.set(key, "off", "Turned off in settings")
        if self.state == "stopped":
            return
        off("webcam", cfg["gestures"]["enabled"]); off("hand_tracking", cfg["gestures"]["enabled"])
        off("cursor", cfg["gestures"]["enabled"]); off("scrolling", cfg["gestures"]["enabled"])
        off("voice", cfg["voice"]["enabled"]); off("microphone", cfg["voice"]["enabled"])
        off("dictation", cfg["voice"]["enabled"]); off("browser", cfg["browser"]["enabled"])

    # --------------------------------------------------------- lifecycle
    def start(self) -> None:
        with self._lock:
            if self.state != "stopped" or self.stopping:
                return
            self.state = "running"
            self.last_stop_reason = ""
        self.log.info("Starting Handsfree...")
        self._start_features()

    def _start_features(self) -> None:
        cfg = self.cfg
        if not self.actions.available:
            self.log.error("Can't control the mouse/keyboard on this machine.")
        if cfg["gestures"]["enabled"]:
            self.gestures.start()
        if cfg["voice"]["enabled"]:
            self.speech.start()
            self.status.set("dictation", "idle", "Say 'start dictation'")
        if cfg["browser"]["enabled"]:
            self.browser.start()
        self._sync_disabled_status()
        self._start_hotkeys()

    def _start_hotkeys(self) -> None:
        hk = self.cfg["hotkeys"]
        if not hk["enabled"]:
            self.hotkeys.stop()
            return
        self.hotkeys.start({
            hk["toggle_scroll"]: lambda: self.state == "running" and self.toggle_scroll(),
            hk["push_to_talk"]: lambda: self.state == "running" and self.session.arm(),
            hk["emergency_stop"]: lambda: self.emergency_stop("emergency shortcut"),
        })

    def _stop_features(self) -> None:
        """Runs in a worker thread: waits for every engine to finish releasing its device."""
        self.hotkeys.stop()
        self.gestures.request_stop(); self.speech.request_stop()
        self.gestures.stop(); self.speech.stop()
        self.browser.stop()
        self.status.set("dictation", "stopped", "")
        self.stopping = False
        self.log.info("Everything stopped. Camera and microphone released.")

    def stop(self, reason: str = "") -> None:
        with self._lock:
            if self.state == "stopped":
                return
            self.state = "stopped"
            self.stopping = True
            self.last_stop_reason = reason
        self.confirm.cancel(); self.calibrator.cancel()
        self.actions.release_all()
        self.session.reset()
        self.modes.reset()
        self.gestures.request_stop(); self.speech.request_stop()
        threading.Thread(target=self._stop_features, name="stopper", daemon=True).start()

    def emergency_stop(self, reason: str = "button") -> None:
        if self.state == "stopped" and not self.stopping:
            return
        self.log.error(f"EMERGENCY STOP ({reason}). Pinch clicking switched OFF.")
        if self.cfg["click"]["enabled"]:
            self.update_setting("click.enabled", False)
        self.stop(f"Emergency stop: {reason}")

    def pause(self) -> None:
        with self._lock:
            if self.state != "running":
                return
            self.state = "paused"
        self.actions.release_all()
        self.status.set("voice", "paused", "Only 'resume' works")
        self.log.info("Paused.")

    def resume(self) -> None:
        with self._lock:
            if self.state != "paused":
                return
            self.state = "running"
        if self.speech.running:
            self.status.set("voice", "running", "Waiting for a command")
        self.log.info("Resumed.")

    def shutdown(self) -> None:
        """Called on Exit: synchronous, so nothing is left holding the camera or mic."""
        with self._lock:
            self.state = "stopped"
        self.confirm.cancel(); self.calibrator.cancel()
        self.actions.release_all()
        self.hotkeys.stop()
        self.gestures.stop(); self.speech.stop()
        self.browser.stop()
        self.cm.save(self.cfg)

    # ------------------------------------------------------------- modes
    def _on_mode_change(self, old: Mode, new: Mode) -> None:
        self.log.info(f"Mode: {new.value}")
        if new == Mode.DICTATION:
            self.session.formatter.reset()
            self.status.set("dictation", "running", "Listening - say 'stop dictation' to finish")
        elif old == Mode.DICTATION:
            self.status.set("dictation", "idle" if self.speech.running else "stopped", "Say 'start dictation'")

    def set_mode(self, mode: Mode) -> None:
        if mode == Mode.DICTATION and not (self.speech.running and self.state != "stopped"):
            self.log.warn("Turn on Voice control and press Start before using Dictation Mode.")
            return
        self.modes.set(mode)

    def toggle_scroll(self) -> None:
        if self.state == "stopped":
            self.log.info("Press Start first.")
            return
        self.modes.toggle_scroll()

    def stop_dictation(self) -> None:
        self.modes.leave_dictation()

    # ---------------------------------------------------------- settings
    def apply_config(self, new_cfg: dict) -> tuple[dict, list[str]]:
        """Validate -> save -> push to the running modules."""
        clean, warnings = self.cm.validate(new_cfg)
        old, self.cfg = self.cfg, clean
        self.cm.save(clean)
        for w in warnings:
            self.log.warn(w)
        if self.state != "stopped":
            self._apply_live_changes(old, clean)
        elif clean["voice"]["enabled"] and not old["voice"]["enabled"]:
            self.log.info("Voice control is ON - it will start when you press Start.")
        self.log.info("Settings saved and applied.")
        return clean, warnings

    def _changed(self, old: dict, new: dict, *paths: str) -> bool:
        return any(get_path(old, p) != get_path(new, p) for p in paths)

    def _apply_live_changes(self, old: dict, new: dict) -> None:
        if self._changed(old, new, "gestures.enabled", "camera.index", "camera.resolution", "gestures.model"):
            threading.Thread(target=self._restart_gestures, daemon=True).start()
        if self._changed(old, new, "voice.enabled", "voice.microphone", "voice.energy_threshold",
                         "speech.engine", "speech.language", "speech.vosk_model"):
            threading.Thread(target=self._restart_speech, daemon=True).start()
        if self._changed(old, new, "browser.enabled"):
            self.browser.start() if new["browser"]["enabled"] else self.browser.stop()
        if self._changed(old, new, "hotkeys.enabled", "hotkeys.toggle_scroll", "hotkeys.push_to_talk", "hotkeys.emergency_stop"):
            self._start_hotkeys()
        self._sync_disabled_status()

    def _restart_gestures(self) -> None:
        self.gestures.stop()
        if self.state != "stopped" and self.cfg["gestures"]["enabled"]:
            self.gestures.start()
        else:
            self.status.set("webcam", "off", "Turned off in settings")
            for k in ("hand_tracking", "cursor", "scrolling"):
                self.status.set(k, "off", "Turned off in settings")

    def _restart_speech(self) -> None:
        self.speech.stop()
        if self.state != "stopped" and self.cfg["voice"]["enabled"]:
            self.speech.start()
        else:
            for k in ("voice", "microphone", "dictation"):
                self.status.set(k, "off", "Turned off in settings")
            self.modes.leave_dictation()

    def update_setting(self, dotted: str, value) -> None:
        """Change one setting (used by the dashboard quick switches)."""
        cfg = copy.deepcopy(self.cfg)
        set_path(cfg, dotted, value)
        self.apply_config(cfg)

    def set_click_enabled(self, on: bool) -> None:
        self.update_setting("click.enabled", bool(on))

    # ------------------------------------------------------- calibration
    def start_calibration(self) -> None:
        if self.state == "stopped" or not self.gestures.running:
            self.log.warn("Press Start first so the camera is on, then calibrate.")
            return
        self.calibrator.start()
        self.log.info("Calibration started - follow the instructions on screen.")

    def cancel_calibration(self) -> None:
        self.calibrator.cancel()

    def _on_calibration_done(self, area: dict) -> None:
        if not area:
            self.log.warn("That area was too small - move your hand further apart and try again.")
            return
        cfg = copy.deepcopy(self.cfg)
        cfg["cursor"]["area"] = area
        self.apply_config(cfg)
        self.log.info("Tracking area calibrated.")

    def reset_area(self) -> None:
        cfg = copy.deepcopy(self.cfg)
        cfg["cursor"]["area"] = copy.deepcopy(self.cm.defaults()["cursor"]["area"])
        self.apply_config(cfg)

    # ----------------------------------------------------- model download
    def download_model_for_language(self) -> None:
        if self.model_download["active"]:
            return
        name = LANG_MODELS.get(self.cfg["speech"]["language"], "vosk-model-small-en-us-0.15")
        threading.Thread(target=self._download, args=(name,), daemon=True).start()

    def _download(self, name: str) -> None:
        md = self.model_download
        md.update(active=True, progress=0.0, message="Starting download...", done_name="")
        try:
            download_model(name, lambda p, m: md.update(progress=p, message=m))
            self.log.info(f"Offline model '{name}' installed.")
            self.update_setting("speech.vosk_model", name)
            md.update(message="Model installed", done_name=name)
        except Exception as exc:
            md.update(message=f"Download failed: {exc}")
            self.log.error(f"Model download failed: {exc}")
        finally:
            md["active"] = False
