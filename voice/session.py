"""Decides what to do with each phrase heard: wake phrase / push-to-talk gating,
yes/no confirmations, dictation typing, and command execution."""
from __future__ import annotations

import time

from core.mode_manager import Mode
from voice.command_router import CommandRouter
from voice.commands import EMERGENCY, NO, YES, normalize, parse_command, strip_wake_phrase
from voice.dictation import DictationFormatter


class VoiceSession:
    def __init__(self, controller):
        self.c = controller
        self.router = CommandRouter(controller)
        self.formatter = DictationFormatter()
        self.awake_until = 0.0

    def arm(self) -> None:
        """Push-to-talk / wake phrase heard: accept commands for the listening window."""
        self.awake_until = time.time() + self.c.cfg["voice"]["listen_window"]
        self.c.status.set_info("last_heard", "Listening - say a command...")
        self.c.log.info("Listening for a command...")

    def reset(self) -> None:
        self.awake_until = 0.0
        self.formatter.reset()

    def handle_text(self, text: str) -> None:
        c = self.c
        cfg = c.cfg
        t = normalize(text)
        if not t or c.state == "stopped":
            return
        c.status.set_info("last_heard", text)

        if c.confirm.has_pending() and (t in YES or t in NO):
            c.confirm.resolve(t in YES)
            return
        if t in EMERGENCY:
            c.emergency_stop("voice command")
            return
        if c.modes.mode == Mode.DICTATION:
            self._dictate(text, t)
            return

        voice = cfg["voice"]
        now = time.time()
        body = t
        if voice["activation"] == "wake_phrase":
            rest = strip_wake_phrase(t, voice["wake_phrase"])
            if rest is not None:
                if not rest:
                    self.arm()
                    return
                body = rest
            elif now > self.awake_until:
                c.log.info(f"Heard \"{text}\" - ignored. Say \"{voice['wake_phrase']}\" first.")
                return                                  # not for us
        elif voice["activation"] == "push_to_talk" and now > self.awake_until:
            c.log.info(f"Heard \"{text}\" - ignored. Press the Talk button / shortcut first.")
            return

        if body in EMERGENCY:
            c.emergency_stop("voice command")
            return
        cmd = parse_command(body, voice["apps"])
        if cmd is None:
            c.log.warn(f"Didn't understand: \"{body}\"  (say 'help' for commands)")
            return
        if voice["activation"] != "always":
            self.awake_until = now + voice["listen_window"]
        self.router.execute(cmd)

    def _dictate(self, text: str, t: str) -> None:
        c = self.c
        d = c.cfg["dictation"]
        stop = normalize(d["stop_phrase"])
        if c.state == "paused":
            return
        if t in (stop, "stop dictating", "end dictation"):
            c.stop_dictation()
            return
        if t == "scratch that":
            n = self.formatter.undo_length()
            if n:
                c.actions.press("backspace", presses=n)
                c.log.info("Removed the last phrase.")
            return
        out = self.formatter.format(text, d["punctuation_commands"], d["auto_capitalize"])
        if out:
            c.actions.type_text(out)
            c.status.set_info("last_action", f"Typed: {out.strip()[:40]}")
