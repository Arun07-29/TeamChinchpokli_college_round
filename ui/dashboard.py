"""The main Handsfree window: big status, big buttons, live camera, live status list."""
from __future__ import annotations

import tkinter as tk

import customtkinter as ctk
from PIL import Image

from core.mode_manager import Mode
from ui import theme
from ui.settings_window import SettingsWindow
from ui.status_panel import StatusPanel

PREVIEW_SIZE = (640, 360)              # starting size; grows with the window at the camera's shape


def _card(master, **kw):
    return ctk.CTkFrame(master, fg_color=theme.CARD, corner_radius=16, border_width=1,
                        border_color=theme.BORDER, **kw)


class Dashboard(ctk.CTk):
    def __init__(self, controller):
        super().__init__()
        self.c = controller
        ctk.set_appearance_mode(controller.cfg["general"]["theme"])
        self.title("Handsfree")
        self.geometry("1280x820")
        self.minsize(1080, 720)
        if self.tk.call("tk", "windowingsystem") == "win32":
            self.after(0, lambda: self.state("zoomed"))          # open maximised: biggest camera view
        self.configure(fg_color=theme.BG)
        self.protocol("WM_DELETE_WINDOW", self.on_exit)

        self._settings = None
        self._log_id = 0
        self._last_fid = -1
        self._live = False
        self._placeholder_text = None
        self._img = None
        self._tick_errors = 0
        self._preview_size = PREVIEW_SIZE
        self._box = (0, 0)
        self._aspect = 16 / 9
        self._expanded = False
        self._meter = 0.0

        self._build()
        self.bind("<Key>", self._on_key)
        self.bind("<Escape>", lambda e: self._toggle_expand(False))
        self.after(100, self._tick)
        self.after(60, self._tick_preview)
        if controller.cfg["general"]["auto_start"]:
            self.after(600, controller.start)

    # ------------------------------------------------------------------ layout
    def _build(self) -> None:
        f_title = ctk.CTkFont(size=26, weight="bold")
        f_h = ctk.CTkFont(size=16, weight="bold")
        f_small = ctk.CTkFont(size=12)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        pad = dict(padx=24)

        # --- header -------------------------------------------------------
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(20, 6), **pad)
        self._header = header
        header.grid_columnconfigure(0, weight=1)
        left = ctk.CTkFrame(header, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(left, text="✋  Handsfree", font=f_title, text_color=theme.TEXT).pack(anchor="w")
        ctk.CTkLabel(left, text="Control your computer with your hand and your voice.",
                     font=f_small, text_color=theme.MUTED).pack(anchor="w")
        right = ctk.CTkFrame(header, fg_color="transparent")
        right.grid(row=0, column=1, sticky="e")
        self.state_badge = ctk.CTkLabel(right, text="● Stopped", width=140, height=36, corner_radius=18,
                                        fg_color=theme.CARD, text_color=theme.NEUTRAL,
                                        font=ctk.CTkFont(size=14, weight="bold"))
        self.state_badge.pack(side="left", padx=6)
        self.mode_badge = ctk.CTkLabel(right, text="Cursor Mode", width=150, height=36, corner_radius=18,
                                       fg_color=theme.ACCENT, text_color="white",
                                       font=ctk.CTkFont(size=14, weight="bold"))
        self.mode_badge.pack(side="left", padx=6)
        ctk.CTkButton(right, text="⚙  Settings", width=120, height=36, corner_radius=18,
                      fg_color=theme.CARD_ALT, hover_color=theme.BORDER, text_color=theme.TEXT,
                      font=ctk.CTkFont(size=14, weight="bold"), command=self._open_settings).pack(side="left", padx=(6, 0))

        # --- control bar --------------------------------------------------
        bar = _card(self)
        bar.grid(row=1, column=0, sticky="ew", pady=8, **pad)
        for i in range(5):
            bar.grid_columnconfigure(i, weight=1, uniform="b")
        def btn(col, text, fg, hover, cmd, outline=False):
            b = ctk.CTkButton(bar, text=text, height=46, corner_radius=12, command=cmd,
                              font=ctk.CTkFont(size=14, weight="bold"),
                              fg_color=("transparent" if outline else fg), hover_color=hover,
                              border_width=2 if outline else 0, border_color=theme.BORDER,
                              text_color=theme.TEXT if outline else "white")
            b.grid(row=0, column=col, padx=8, pady=12, sticky="ew")
            return b
        self.btn_start = btn(0, "▶  Start", theme.GOOD, theme.GOOD_HOVER, self.c.start)
        self.btn_pause = btn(1, "⏸  Pause", theme.WARN, theme.WARN_HOVER, self.c.pause)
        self.btn_resume = btn(2, "⏵  Resume", theme.ACCENT, theme.ACCENT_HOVER, self.c.resume)
        self.btn_estop = btn(3, "⬛  EMERGENCY STOP", theme.BAD, theme.BAD_HOVER, lambda: self.c.emergency_stop("button"))
        self.btn_exit = btn(4, "Exit", theme.CARD_ALT, theme.BORDER, self.on_exit, outline=True)

        # --- banners (hidden until needed) -----------------------------------
        self.confirm_banner = ctk.CTkFrame(self, fg_color=theme.BANNER, corner_radius=14, border_width=1, border_color=theme.WARN)
        self.confirm_label = ctk.CTkLabel(self.confirm_banner, text="", font=f_h, text_color=theme.TEXT, anchor="w")
        self.confirm_label.pack(side="left", padx=16, pady=12)
        ctk.CTkButton(self.confirm_banner, text="No", width=80, fg_color=theme.CARD_ALT, hover_color=theme.BORDER,
                      text_color=theme.TEXT, command=lambda: self.c.confirm.resolve(False)).pack(side="right", padx=(0, 14))
        ctk.CTkButton(self.confirm_banner, text="Yes, do it", width=110, fg_color=theme.GOOD, hover_color=theme.GOOD_HOVER,
                      command=lambda: self.c.confirm.resolve(True)).pack(side="right", padx=6)
        ctk.CTkLabel(self.confirm_banner, text="or say “yes” / “no”", font=f_small, text_color=theme.MUTED).pack(side="right", padx=8)

        self.calib_banner = ctk.CTkFrame(self, fg_color=theme.BANNER, corner_radius=14, border_width=1, border_color=theme.ACCENT)
        self.calib_label = ctk.CTkLabel(self.calib_banner, text="", font=f_h, text_color=theme.TEXT, anchor="w")
        self.calib_label.pack(side="left", padx=16, pady=12)
        ctk.CTkButton(self.calib_banner, text="Cancel", width=90, fg_color=theme.CARD_ALT, hover_color=theme.BORDER,
                      text_color=theme.TEXT, command=self.c.cancel_calibration).pack(side="right", padx=14)
        self._banner_shown = {"confirm": False, "calib": False}

        # --- content ------------------------------------------------------------
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=3, column=0, sticky="nsew", pady=(2, 20), **pad)
        content.grid_columnconfigure(0, weight=5)
        content.grid_columnconfigure(1, weight=2, minsize=340)
        self._content = content
        content.grid_rowconfigure(0, weight=1)

        # left column: camera + quick controls
        lcol = ctk.CTkFrame(content, fg_color="transparent")
        lcol.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        lcol.grid_columnconfigure(0, weight=1)
        lcol.grid_rowconfigure(0, weight=1)

        cam = _card(lcol)
        cam.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        cam_head = ctk.CTkFrame(cam, fg_color="transparent")
        cam_head.pack(fill="x", padx=18, pady=(12, 6))
        self.cam_title = ctk.CTkLabel(cam_head, text="Camera", font=f_h, text_color=theme.TEXT)
        self.cam_title.pack(side="left")
        self.expand_btn = ctk.CTkButton(cam_head, text="⛶  Full-screen camera", width=170, height=30, corner_radius=15,
                                        fg_color=theme.CARD_ALT, hover_color=theme.BORDER, text_color=theme.TEXT,
                                        font=ctk.CTkFont(size=13, weight="bold"), command=self._toggle_expand)
        self.expand_btn.pack(side="right")
        self._blank_src = Image.new("RGB", (64, 36), (22, 25, 36))
        self._blank = ctk.CTkImage(self._blank_src, size=PREVIEW_SIZE)
        self.preview_box = ctk.CTkFrame(cam, fg_color="transparent")
        self.preview_box.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.preview = ctk.CTkLabel(self.preview_box, text="", image=self._blank, compound="center",
                                    text_color="#9AA3B5", font=ctk.CTkFont(size=16), corner_radius=10)
        self.preview.place(relx=0.5, rely=0.5, anchor="center")
        self.preview_box.bind("<Configure>", self._on_preview_resize)

        quick = _card(lcol)
        quick.grid(row=1, column=0, sticky="ew")
        self._quick = quick
        quick.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="q")
        self.mode_seg = ctk.CTkSegmentedButton(quick, values=[m.short for m in Mode],
                                               command=lambda v: self.c.set_mode(Mode.from_short(v)),
                                               font=ctk.CTkFont(size=13, weight="bold"), height=34)
        self.mode_seg.grid(row=0, column=0, columnspan=3, sticky="ew", padx=(18, 6), pady=(14, 8))
        self.mode_seg.set("Cursor")

        def switch(row, col, text, hint, path):
            box = ctk.CTkFrame(quick, fg_color="transparent")
            box.grid(row=row, column=col, sticky="w", padx=(18, 4), pady=2)
            sw = ctk.CTkSwitch(box, text=text, font=ctk.CTkFont(size=13, weight="bold"),
                               command=lambda: self.c.update_setting(path, bool(sw.get())))
            sw.pack(anchor="w")
            ctk.CTkLabel(box, text=hint, font=ctk.CTkFont(size=11), text_color=theme.MUTED).pack(anchor="w", padx=(46, 0))
            return sw
        self.sw_click = switch(1, 0, "Pinch to click", "Thumb + index", "click.enabled")
        self.sw_hands = switch(1, 1, "Hand tracking", "Pointer follows hand", "gestures.enabled")
        self.sw_voice = switch(1, 2, "Voice control", "“hey handsfree …”", "voice.enabled")
        self.sw_browser = switch(1, 3, "Browser control", "Tabs, search", "browser.enabled")
        self.talk_btn = ctk.CTkButton(quick, text="🎤  Talk now", height=34, corner_radius=10,
                                      fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                                      font=ctk.CTkFont(size=13, weight="bold"), command=self.c.session.arm)
        self.talk_btn.grid(row=0, column=3, sticky="ew", padx=(6, 18), pady=(14, 8))
        ctk.CTkLabel(quick, text="Gestures:  pinch thumb + index = click (hold to drag)  ·  thumb + middle = right-click  ·  "
                                 "index + middle up = scroll  ·  fist = hold pointer still.\n"
                                 "Shortcuts:  S = Scroll Mode   C = Pinch click   E = Full-screen camera (Esc to leave)   F8 = Scroll Mode (anywhere)   F9 = Talk   "
                                 "F12 = Emergency stop", font=ctk.CTkFont(size=11), text_color=theme.MUTED,
                     wraplength=760, justify="left").grid(row=2, column=0, columnspan=4, sticky="w", padx=18, pady=(4, 12))

        # right column: status + activity
        rcol = ctk.CTkFrame(content, fg_color="transparent")
        rcol.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self._rcol = rcol
        rcol.grid_columnconfigure(0, weight=1)
        rcol.grid_rowconfigure(1, weight=1)
        self.status_panel = StatusPanel(rcol)
        self.status_panel.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        act = _card(rcol)
        act.grid(row=1, column=0, sticky="nsew")
        act.grid_columnconfigure(0, weight=1)
        act.grid_rowconfigure(3, weight=1)
        ctk.CTkLabel(act, text="Activity", font=f_h, text_color=theme.TEXT).grid(row=0, column=0, sticky="w", padx=18, pady=(14, 0))
        self.heard_label = ctk.CTkLabel(act, text="🎤  Voice is off", font=ctk.CTkFont(size=12), text_color=theme.MUTED,
                                        anchor="w", justify="left", wraplength=360)
        self.heard_label.grid(row=1, column=0, sticky="ew", padx=18, pady=(2, 2))
        meter = ctk.CTkFrame(act, fg_color="transparent")
        meter.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 6))
        ctk.CTkLabel(meter, text="Mic level", font=ctk.CTkFont(size=11), text_color=theme.MUTED).pack(side="left")
        self.mic_bar = ctk.CTkProgressBar(meter, height=8, progress_color=theme.GOOD)
        self.mic_bar.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self.mic_bar.set(0)
        self.log_box = ctk.CTkTextbox(act, height=110, wrap="word", state="disabled", fg_color=theme.CARD_ALT,
                                      font=ctk.CTkFont(family="Consolas", size=11), corner_radius=10)
        self.log_box.grid(row=3, column=0, sticky="nsew", padx=14, pady=(0, 14))
        try:
            tb = self.log_box._textbox
            tb.tag_config("error", foreground="#EF4444")
            tb.tag_config("warn", foreground="#F59E0B")
        except Exception:
            pass

    # ------------------------------------------------------------------ actions
    def _open_settings(self) -> None:
        if self._settings is not None and self._settings.winfo_exists():
            self._settings.lift()
            self._settings.focus()
            return
        self._settings = SettingsWindow(self, self.c, on_saved=self._on_settings_saved)

    def _toggle_expand(self, force: bool | None = None) -> None:
        """Big camera view: full screen, side panels hidden. Only the Start/Stop bar stays (safety)."""
        want = (not self._expanded) if force is None else force
        if want == self._expanded:
            return
        self._expanded = want
        if want:
            self._rcol.grid_remove()
            self._quick.grid_remove()
            self._header.grid_remove()
            self._content.grid_columnconfigure(1, weight=0, minsize=0)
            self.attributes("-fullscreen", True)
            self.expand_btn.configure(text="▣  Normal view  (Esc)")
        else:
            self.attributes("-fullscreen", False)
            self._rcol.grid()
            self._quick.grid()
            self._header.grid()
            self._content.grid_columnconfigure(1, weight=2, minsize=340)
            self.expand_btn.configure(text="⛶  Full-screen camera")
            if self.tk.call("tk", "windowingsystem") == "win32":
                self.after(50, lambda: self.state("zoomed"))

    def _on_preview_resize(self, event) -> None:
        try:
            scale = ctk.ScalingTracker.get_widget_scaling(self)
        except Exception:
            scale = 1.0
        self._box = (event.width / scale, event.height / scale)
        self._fit_preview()

    def _fit_preview(self) -> None:
        """Fit the preview into its area at the camera's own shape (16:9 for 720p, 4:3 for 480p).
        CTkImage sizes are in unscaled units."""
        w, h = self._box
        if w < 50 or h < 50:
            return
        pw = max(160, min(w, h * self._aspect))
        size = (int(pw), int(pw / self._aspect))
        if abs(size[0] - self._preview_size[0]) < 4 and abs(size[1] - self._preview_size[1]) < 4:
            return
        self._preview_size = size
        self._blank = ctk.CTkImage(self._blank_src, size=size)
        if not self._live:
            self.preview.configure(image=self._blank)

    def _on_settings_saved(self, cfg: dict) -> None:
        ctk.set_appearance_mode(cfg["general"]["theme"])

    def _on_key(self, event) -> None:
        if isinstance(self.focus_get(), (tk.Entry, tk.Text)):
            return
        ch = (event.char or "").lower()
        if ch == "s":
            self.c.toggle_scroll()
        elif ch == "c":
            self.c.update_setting("click.enabled", not self.c.cfg["click"]["enabled"])
        elif ch == "e":
            self._toggle_expand()

    def on_exit(self) -> None:
        self.state_badge.configure(text="Closing...", text_color=theme.WARN)
        self.update_idletasks()
        try:
            self.c.shutdown()
        finally:
            self.destroy()

    # ------------------------------------------------------------------ refresh
    def _tick(self) -> None:
        try:
            self._refresh()
        except Exception as exc:                     # keep the UI alive no matter what
            self._tick_errors += 1
            if self._tick_errors < 5:
                self.c.log.error(f"UI refresh problem: {exc}")
        self.after(150, self._tick)

    def _refresh(self) -> None:
        c = self.c
        snap = c.status.snapshot()
        cfg = c.cfg

        # state badge + buttons
        if c.stopping:
            text, col = "● Stopping...", theme.WARN
        else:
            text, col = {"stopped": ("● Stopped", theme.NEUTRAL), "running": ("● Running", theme.GOOD),
                         "paused": ("● Paused", theme.WARN)}[c.state]
        self.state_badge.configure(text=text, text_color=col)
        self.mode_badge.configure(text=c.modes.mode.value)
        self._set_enabled(self.btn_start, c.state == "stopped" and not c.stopping)
        self._set_enabled(self.btn_pause, c.state == "running")
        self._set_enabled(self.btn_resume, c.state == "paused")
        self._set_enabled(self.btn_estop, c.state != "stopped")

        # mode + switches (reflect reality, e.g. after a voice command)
        if self.mode_seg.get() != c.modes.mode.short:
            self.mode_seg.set(c.modes.mode.short)
        for sw, val in ((self.sw_click, cfg["click"]["enabled"]), (self.sw_hands, cfg["gestures"]["enabled"]),
                        (self.sw_voice, cfg["voice"]["enabled"]), (self.sw_browser, cfg["browser"]["enabled"])):
            if bool(sw.get()) != val:
                sw.select() if val else sw.deselect()
        self._set_enabled(self.talk_btn, c.speech.running and c.state == "running")

        self.status_panel.update_status(snap["features"])
        c.gestures.preview_wanted = self.state() != "iconic"          # don't draw frames nobody sees
        fps = c.gestures.fps if c.gestures.running else 0
        cam_text = f"Camera  ·  {fps:.0f} fps" if fps else "Camera"
        if self.cam_title.cget("text") != cam_text:
            self.cam_title.configure(text=cam_text)

        level = snap["info"].get("mic_level", 0.0) if c.speech.running else 0.0
        self._meter = max(level ** 0.5, self._meter * 0.6)       # sqrt: quiet speech still moves the bar
        self.mic_bar.set(self._meter)

        heard = snap["info"]["last_heard"]
        partial = snap["info"].get("partial", "")
        if not cfg["voice"]["enabled"]:
            self.heard_label.configure(text="🎤  Voice is off - flip “Voice control” to turn it on")
        elif partial:
            self.heard_label.configure(text=f"🎤  Hearing: “{partial}…”")
        elif heard:
            self.heard_label.configure(text=f"🎤  Heard: “{heard}”")
        else:
            self.heard_label.configure(text=f"🎤  Say “{cfg['voice']['wake_phrase']}” then a command, e.g. “scroll down”")

        # banners
        pending = c.confirm.current()
        self._show_banner("confirm", self.confirm_banner, pending is not None)
        if pending:
            self.confirm_label.configure(text=f"⚠  {pending[0]}   ({int(pending[1])}s)")
        calib = c.calibrator.active
        self._show_banner("calib", self.calib_banner, calib)
        if calib:
            self.calib_label.configure(text="🎯  " + (snap["info"]["calibration"] or c.calibrator.prompt))

        # activity log
        items = c.log.since(self._log_id)
        if items:
            self._log_id = items[-1][0]
            tb = self.log_box._textbox
            self.log_box.configure(state="normal")
            for _, ts, level, text_ in items:
                tb.insert("end", f"{ts}  {text_}\n", level)
            tb.see("end")
            self.log_box.configure(state="disabled")

    def _show_banner(self, key: str, frame, show: bool) -> None:
        if show and not self._banner_shown[key]:
            frame.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 6))
        elif not show and self._banner_shown[key]:
            frame.grid_remove()
        self._banner_shown[key] = show

    @staticmethod
    def _set_enabled(button, enabled: bool) -> None:
        want = "normal" if enabled else "disabled"
        if button.cget("state") != want:
            button.configure(state=want)

    def _tick_preview(self) -> None:
        try:
            fid, frame = self.c.gestures.get_frame()
            if frame is not None:
                if fid != self._last_fid:
                    self._last_fid = fid
                    fh, fw = frame.shape[:2]
                    if abs(fw / fh - self._aspect) > 0.01:          # camera shape changed (720p / 480p)
                        self._aspect = fw / fh
                        self._fit_preview()
                    img = Image.fromarray(frame)
                    self._img = ctk.CTkImage(light_image=img, dark_image=img, size=self._preview_size)
                    self.preview.configure(image=self._img, text="")
                    self._live = True
            else:
                self._show_placeholder()
        except Exception:
            pass
        self.after(40, self._tick_preview)

    def _show_placeholder(self) -> None:
        c = self.c
        if c.state == "stopped":
            text = "Camera is off\nPress  ▶ Start  to begin"
        elif not c.cfg["gestures"]["enabled"]:
            text = "Hand tracking is off"
        elif c.gestures.running and not c.cfg["general"]["show_preview"]:
            text = "Preview hidden (tracking still works)"
        elif c.status.snapshot()["features"]["webcam"][0] == "error":
            text = "Camera problem - see the status list"
        else:
            text = "Starting camera..."
        if self._live or text != self._placeholder_text:
            self.preview.configure(image=self._blank, text=text)
            self._placeholder_text = text
            self._live = False
            self._last_fid = -1
