"""Runs a parsed Command using the app's modules."""
from __future__ import annotations

import os
import shlex
import subprocess

from browser.browser_controller import RISKY
from core.mode_manager import Mode
from voice.commands import Command, HELP_TEXT, normalize_site

ALLOWED_WHILE_PAUSED = {"resume", "pause"}


class CommandRouter:
    def __init__(self, controller):
        self.c = controller

    def execute(self, cmd: Command) -> None:
        c, log = self.c, self.c.log
        if c.state == "paused" and cmd.name not in ALLOWED_WHILE_PAUSED:
            log.info("Paused - say 'hey handsfree resume' to continue.")
            return
        cfg = c.cfg
        a = c.actions
        n, args = cmd.name, cmd.args
        try:
            if n == "click": a.click(); done = "Click"
            elif n == "double_click": a.double_click(); done = "Double click"
            elif n == "right_click": a.right_click(); done = "Right click"
            elif n == "scroll":
                a.scroll_notches(args["notches"] * (1 if args["direction"] == "up" else -1))
                done = f"Scroll {args['direction']}"
            elif n == "key": a.press(args["key"]); done = f"Pressed {args['key']}"
            elif n == "type": a.type_text(args["text"]); done = f"Typed '{args['text']}'"
            elif n == "mode":
                c.set_mode(Mode.from_short(args["mode"])); done = f"{args['mode']} mode"
            elif n == "dictation_start": c.set_mode(Mode.DICTATION); done = "Dictation started"
            elif n == "pause": c.pause(); done = "Paused"
            elif n == "resume": c.resume(); done = "Resumed"
            elif n == "set_click": c.set_click_enabled(args["on"]); done = "Clicking " + ("ON" if args["on"] else "OFF")
            elif n == "help":
                for line in HELP_TEXT.splitlines():
                    log.info(line)
                done = "Help shown"
            elif n == "system":
                self._system(args["action"]); done = args["action"].replace("_", " ").capitalize()
            elif n == "open_app": done = self._open_app(args["name"])
            elif n == "browser": done = self._browser(args)
            else:
                log.warn(f"Unknown command '{n}'"); return
            if done:
                c.status.set_info("last_action", done)
                log.info(f"Did: {done}")
        except Exception as exc:
            log.error(f"Couldn't do '{n}': {exc}")

    # ------------------------------------------------------------------
    def _browser(self, args: dict) -> str:
        c = self.c
        if not c.cfg["browser"]["enabled"] or not c.browser.active:
            c.log.warn("Browser controls are turned off (Settings > Browser).")
            return ""
        action = args["action"]
        if action in RISKY and c.cfg["browser"]["confirm_risky"]:
            if action == "go_to":
                prompt = f"Open {c.browser.resolve_target(args['target'])} ?"
            else:
                prompt = "Close the " + ("tab" if action == "close_tab" else "browser window") + "?"
            c.confirm.request(prompt, lambda: c.log.info("Did: " + c.browser.perform(action, **{k: v for k, v in args.items() if k != "action"})))
            return ""
        return c.browser.perform(action, **{k: v for k, v in args.items() if k != "action"})

    def _system(self, action: str) -> None:
        a = self.c.actions
        if action == "switch_window": a.hotkey("alt", "tab")
        elif action == "show_desktop": a.hotkey("win", "d")

    def _open_app(self, name: str) -> str:
        apps = self.c.cfg["voice"]["apps"]
        command = apps.get(name)
        if not command:
            self.c.log.warn(f"'{name}' isn't in your allowed apps. Add it in Settings > Voice.")
            return ""
        if os.name == "nt" and " " not in command.strip():
            os.startfile(command)                                  # noqa: S606 (user-configured)
        else:
            subprocess.Popen(shlex.split(command, posix=(os.name != "nt")))
        return f"Opened {name}"
