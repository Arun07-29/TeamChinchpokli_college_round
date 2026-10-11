"""Settings window. Every control here is saved to config.json AND applied to the running app."""
from __future__ import annotations

import copy
import threading

import customtkinter as ctk

from config_manager import LANGUAGES, SEARCH_ENGINES, ConfigManager
from core.mode_manager import Mode
from ui import theme
from voice.commands import HELP_TEXT
from voice.microphones import list_microphones
from voice.model_manager import list_models

ATOMIC = {"apps", "area"}          # saved as a whole, not key-by-key
PINCH_LABELS = [("off", "Off"), ("thumb_middle", "Thumb + middle finger"),
                ("thumb_ring", "Thumb + ring finger"), ("thumb_pinky", "Thumb + little finger")]


def _diff_apply(base: dict, draft: dict, target: dict) -> None:
    """Copy only the values the user actually changed in this window onto ``target``."""
    for key, val in draft.items():
        if isinstance(val, dict) and key not in ATOMIC:
            _diff_apply(base.get(key, {}), val, target.setdefault(key, {}))
        elif base.get(key) != val:
            target[key] = val


class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, master, controller, on_saved=None):
        super().__init__(master)
        self.c = controller
        self.on_saved = on_saved
        self.baseline = copy.deepcopy(controller.cfg)
        self.draft = copy.deepcopy(controller.cfg)
        self._getters = []
        self._widgets = {}
        self._after_id = None
        self._cam_result = None
        self._calib_hidden = False
        self._seen_model = ""

        self.title("Handsfree - Settings")
        self.geometry("860x740")
        self.minsize(760, 600)
        self.configure(fg_color=theme.BG)
        self.after(150, self._bring_to_front)
        self._build()
        self._poll()

    def _bring_to_front(self) -> None:
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def destroy(self) -> None:
        if self._after_id:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
        super().destroy()

    # ------------------------------------------------------------ draft helpers
    def _get(self, path):
        d = self.draft
        for k in path:
            d = d[k]
        return d

    def _set(self, path, value) -> None:
        d = self.draft
        for k in path[:-1]:
            d = d[k]
        d[path[-1]] = value

    # ------------------------------------------------------------ builders
    def _build(self) -> None:
        for w in self.winfo_children():
            w.destroy()
        self._getters.clear()
        self._widgets.clear()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 4))
        ctk.CTkLabel(head, text="Settings", font=ctk.CTkFont(size=24, weight="bold"), text_color=theme.TEXT).pack(anchor="w")
        ctk.CTkLabel(head, text="Change anything here, then press “Save & apply”. Changes take effect straight away.",
                     font=ctk.CTkFont(size=12), text_color=theme.MUTED).pack(anchor="w")

        self.tabs = ctk.CTkTabview(self, fg_color=theme.CARD, corner_radius=16, border_width=1, border_color=theme.BORDER,
                                   segmented_button_selected_color=theme.ACCENT,
                                   segmented_button_selected_hover_color=theme.ACCENT_HOVER)
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=22, pady=8)
        names = ["General", "Hand & Cursor", "Scrolling", "Voice", "Dictation", "Browser"]
        pages = {}
        for n in names:
            tab = self.tabs.add(n)
            sf = ctk.CTkScrollableFrame(tab, fg_color="transparent")
            sf.pack(fill="both", expand=True)
            pages[n] = sf
        self._tab_general(pages["General"])
        self._tab_hand(pages["Hand & Cursor"])
        self._tab_scroll(pages["Scrolling"])
        self._tab_voice(pages["Voice"])
        self._tab_dictation(pages["Dictation"])
        self._tab_browser(pages["Browser"])

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=2, column=0, sticky="ew", padx=22, pady=(4, 16))
        foot.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(foot, text="Reset to defaults", width=140, fg_color="transparent", border_width=2,
                      border_color=theme.BORDER, text_color=theme.TEXT, hover_color=theme.CARD_ALT,
                      command=self._reset).grid(row=0, column=0)
        self.msg = ctk.CTkLabel(foot, text="", font=ctk.CTkFont(size=12), text_color=theme.MUTED, wraplength=380, justify="left")
        self.msg.grid(row=0, column=1, padx=12, sticky="w")
        ctk.CTkButton(foot, text="Close", width=90, fg_color=theme.CARD_ALT, hover_color=theme.BORDER,
                      text_color=theme.TEXT, command=self.destroy).grid(row=0, column=2, padx=6)
        ctk.CTkButton(foot, text="Save & apply", width=140, fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                      font=ctk.CTkFont(weight="bold"), command=self._save).grid(row=0, column=3)

    def _section(self, parent, title: str) -> None:
        ctk.CTkLabel(parent, text=title, font=ctk.CTkFont(size=15, weight="bold"), text_color=theme.ACCENT,
                     anchor="w").pack(fill="x", padx=6, pady=(16, 2))

    def _row(self, parent, title: str, help_text: str = ""):
        f = ctk.CTkFrame(parent, fg_color=theme.CARD_ALT, corner_radius=12)
        f.pack(fill="x", pady=4, padx=2)
        f.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(f, text=title, font=ctk.CTkFont(size=13, weight="bold"), text_color=theme.TEXT,
                     anchor="w").grid(row=0, column=0, sticky="w", padx=14, pady=(10, 0 if help_text else 10))
        if help_text:
            ctk.CTkLabel(f, text=help_text, font=ctk.CTkFont(size=11), text_color=theme.MUTED, anchor="w",
                         justify="left", wraplength=400).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 10))
        holder = ctk.CTkFrame(f, fg_color="transparent")
        holder.grid(row=0, column=1, rowspan=2, sticky="e", padx=14)
        return holder

    def _switch(self, parent, title, help_text, path):
        h = self._row(parent, title, help_text)
        var = ctk.BooleanVar(value=bool(self._get(path)))
        sw = ctk.CTkSwitch(h, text="", variable=var, width=46, command=lambda: self._set(path, bool(var.get())))
        sw.pack()
        return sw

    def _slider(self, parent, title, help_text, path, lo, hi, steps, fmt, integer=False):
        h = self._row(parent, title, help_text)
        value = self._get(path)
        lbl = ctk.CTkLabel(h, text=fmt(value), width=64, font=ctk.CTkFont(size=12, weight="bold"), text_color=theme.TEXT)

        def on_change(v):
            v = int(round(v)) if integer else round(float(v), 3)
            self._set(path, v)
            lbl.configure(text=fmt(v))
        s = ctk.CTkSlider(h, from_=lo, to=hi, number_of_steps=steps, width=200, command=on_change)
        s.set(value)
        s.pack(side="left", padx=(0, 8))
        lbl.pack(side="left")
        return s

    def _option(self, parent, title, help_text, path, choices):
        """choices: list of (value, label)."""
        h = self._row(parent, title, help_text)
        labels = [l for _, l in choices]
        by_label = {l: v for v, l in choices}
        by_value = {v: l for v, l in choices}
        cur = self._get(path)
        menu = ctk.CTkOptionMenu(h, values=labels or ["-"], width=230, fg_color=theme.ACCENT,
                                 button_color=theme.ACCENT_HOVER, command=lambda l: self._set(path, by_label[l]))
        menu.set(by_value.get(cur, labels[0] if labels else "-"))
        menu.pack()
        return menu

    def _entry(self, parent, title, help_text, path, width=230):
        h = self._row(parent, title, help_text)
        e = ctk.CTkEntry(h, width=width)
        e.insert(0, str(self._get(path)))
        e.pack()
        self._getters.append(lambda: self._set(path, e.get().strip()))
        return e

    def _button(self, parent, title, help_text, label, command):
        h = self._row(parent, title, help_text)
        b = ctk.CTkButton(h, text=label, width=190, fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER, command=command)
        b.pack()
        return b

    def _note(self, parent, text: str) -> None:
        ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=11), text_color=theme.MUTED, anchor="w",
                     justify="left", wraplength=640).pack(fill="x", padx=8, pady=(2, 6))

    # ------------------------------------------------------------ tabs
    def _tab_general(self, p) -> None:
        self._section(p, "Appearance")
        self._option(p, "Theme", "Dark is easier on the eyes in a dim room.", ("general", "theme"),
                     [("dark", "Dark"), ("light", "Light"), ("system", "Match my computer")])
        self._switch(p, "Show camera preview", "Turn this off to save a little CPU. Tracking keeps working.",
                     ("general", "show_preview"))
        self._section(p, "Startup")
        self._switch(p, "Start automatically", "Begin tracking as soon as Handsfree opens.", ("general", "auto_start"))
        self._section(p, "Shortcuts that work in any window")
        self._switch(p, "Enable global shortcuts", "Needs the 'pynput' package (included in requirements).", ("hotkeys", "enabled"))
        self._entry(p, "Switch Cursor / Scroll mode", "Example: <f8>  or  <ctrl>+<alt>+s", ("hotkeys", "toggle_scroll"))
        self._entry(p, "Talk to Handsfree", "Press once, then speak (used by push-to-talk).", ("hotkeys", "push_to_talk"))
        self._entry(p, "Emergency stop", "Stops everything immediately. Keep this one handy!", ("hotkeys", "emergency_stop"))

    def _cameras(self):
        n = self._get(("camera", "index"))
        return [(i, f"Camera {i}") for i in sorted({0, 1, 2, 3, n})]

    def _tab_hand(self, p) -> None:
        self._section(p, "Camera")
        self._switch(p, "Hand tracking", "Move the mouse pointer with your index fingertip.", ("gestures", "enabled"))
        self._widgets["camera"] = self._option(p, "Webcam", "Pick the camera you want to use. Applies right away.",
                                               ("camera", "index"), self._cameras())
        self._button(p, "Find my cameras", "Looks for connected webcams.", "Refresh camera list", self._refresh_cameras)
        self._option(p, "Camera picture", "720p widescreen: bigger, sharper view and more room for your hand. "
                     "480p: lighter on slow computers. (This webcam's hardware maximum is 30 fps.)",
                     ("camera", "resolution"), [("720p", "720p widescreen (best)"), ("480p", "480p (faster)")])
        self._option(p, "Hand model", "Accurate tracks fingers more precisely; Fast uses less CPU.",
                     ("gestures", "model"), [("accurate", "Accurate"), ("fast", "Fast")])

        self._section(p, "Pointer feel")
        self._slider(p, "Speed", "How far the pointer moves for each hand movement.",
                     ("cursor", "speed"), 0.5, 3.0, 25, lambda v: f"{v:.1f}x")
        self._slider(p, "Smoothing", "Higher = steadier when your hand is still. Fast movements stay responsive "
                     "either way (adaptive filter). Lower = snappier.",
                     ("cursor", "smoothing"), 0.0, 0.95, 38, lambda v: f"{int(round(v * 100))}%")
        self._switch(p, "Smooth pointer (120 Hz)", "The camera gives 30 pictures a second; this glides the pointer "
                     "between them 120 times a second so it moves smoothly instead of in small jumps.", ("cursor", "glide"))
        self._slider(p, "Ignore tiny shakes", "Ignore pointer movements smaller than this many pixels.",
                     ("cursor", "steady_px"), 0, 30, 30, lambda v: f"{int(v)} px", integer=True)

        self._section(p, "Tracking area")
        self.area_label = ctk.CTkLabel(p, text="", font=ctk.CTkFont(size=12), text_color=theme.MUTED, anchor="w")
        self.area_label.pack(fill="x", padx=8)
        self._update_area_label()
        self._button(p, "Calibrate", "Follow two on-screen prompts so the pointer reaches every corner "
                     "without stretching your arm. Handsfree must be started.", "Start calibration", self._calibrate)
        self._button(p, "Reset area", "Go back to the default area.", "Reset tracking area", self._reset_area)

        self._switch(p, "Fist holds the pointer still", "Make a fist to rest your hand without moving the pointer.",
                     ("gestures", "fist_freeze"))

        self._section(p, "Clicking")
        self._switch(p, "Pinch to click  (OFF by default)",
                     "Touch thumb and index finger to click. Test on a harmless page first.", ("click", "enabled"))
        self._slider(p, "Pinch sensitivity", "How close your fingers must get (measured against your hand size, so it "
                     "works near or far from the camera). Bigger = clicks trigger more easily.",
                     ("click", "pinch_ratio"), 0.12, 0.60, 24, lambda v: f"{int(round(v * 100))}%")
        self._slider(p, "Time between clicks", "Stops accidental repeat clicks.",
                     ("click", "cooldown"), 0.1, 3.0, 29, lambda v: f"{v:.2f} s")
        self._switch(p, "Pinch and hold to drag", "Keep pinching to hold the mouse button down (move windows, select "
                     "text, drag files). Open your fingers to drop.", ("click", "drag_enabled"))
        self._slider(p, "Hold time before dragging", "How long to keep pinching before the pointer starts dragging.",
                     ("click", "hold_time"), 0.15, 1.5, 27, lambda v: f"{v:.2f} s")
        self._switch(p, "Dwell click", "Hold the pointer still to click - no pinching needed. Good for tired hands.",
                     ("click", "dwell_enabled"))
        self._slider(p, "Dwell time", "How long to hold still before a dwell click.",
                     ("click", "dwell_time"), 0.5, 3.0, 25, lambda v: f"{v:.1f} s")
        self._option(p, "Right-click gesture", "Touch your thumb to this finger to right-click.",
                     ("click", "right_click_gesture"), PINCH_LABELS)
        self._option(p, "Double-click gesture", "Touch your thumb to this finger to double-click. "
                     "Use a different finger from right-click.", ("click", "double_click_gesture"), PINCH_LABELS)

    def _tab_scroll(self, p) -> None:
        self._section(p, "Scroll Mode")
        self._note(p, "Two ways to scroll. 1) TWO-FINGER SCROLL (always available in Cursor Mode): raise your index and "
                      "middle fingers together with the other fingers folded, then move your hand up or down. The pointer "
                      "stays still while you do this. 2) SCROLL MODE: press S (or F8, or say “scroll mode”) and move your "
                      "whole palm up or down; the pointer and clicks pause. Hold still to stop scrolling.")
        self._switch(p, "Two-finger scroll", "Index + middle finger raised together = scroll.", ("scroll", "two_finger"))
        self._slider(p, "Scroll speed", "How fast the page moves when you move your hand.",
                     ("scroll", "sensitivity"), 0.2, 3.0, 28, lambda v: f"{v:.1f}x")
        self._slider(p, "Dead zone", "How far you must move your hand before scrolling starts. "
                     "Bigger = harder to scroll by accident.", ("scroll", "deadzone"), 0.01, 0.2, 19,
                     lambda v: f"{int(round(v * 100))}%")
        self._switch(p, "Reverse direction", "Swap up and down.", ("scroll", "invert"))

    def _tab_voice(self, p) -> None:
        self._section(p, "Voice commands")
        self._switch(p, "Voice control  (OFF by default)", "Lets you control the computer by speaking.", ("voice", "enabled"))
        mics = [("", "System default (picks a working mic automatically)")] + [(m, m) for m in list_microphones()]
        cur = self._get(("voice", "microphone"))
        if cur and cur not in [m for m, _ in mics]:
            mics.append((cur, f"{cur} (not found)"))
        self._option(p, "Microphone", "Which microphone to listen to.", ("voice", "microphone"), mics)
        self._option(p, "How should I listen?",
                     "Wake phrase: say the phrase first (safest).  Push-to-talk: press the Talk shortcut first.  "
                     "Always listening: every phrase is treated as a command.", ("voice", "activation"),
                     [("wake_phrase", "Wake phrase"), ("push_to_talk", "Push-to-talk"), ("always", "Always listening")])
        self._entry(p, "Wake phrase", "Say this, then your command. e.g. “hey handsfree scroll down”.", ("voice", "wake_phrase"))
        self._slider(p, "Listening window", "After the wake phrase or Talk shortcut, how long I keep listening.",
                     ("voice", "listen_window"), 2, 30, 28, lambda v: f"{v:.0f} s")
        self._slider(p, "Microphone sensitivity", "Leave on Auto unless commands are missed. Lower = more sensitive.",
                     ("voice", "energy_threshold"), 0, 2000, 40, lambda v: "Auto" if int(v) == 0 else f"{int(v)}", integer=True)
        self._switch(p, "Sound cues", "Short beeps: listening, done, didn't understand.", ("voice", "sounds"))

        self._section(p, "Apps I'm allowed to open")
        self._note(p, "One per line:  name = program.  Saying “open notepad” runs the program on the right. "
                      "Only apps listed here can be opened by voice.")
        tb = ctk.CTkTextbox(p, height=130, fg_color=theme.CARD_ALT, font=ctk.CTkFont(family="Consolas", size=12))
        tb.pack(fill="x", padx=4, pady=4)
        tb.insert("1.0", "\n".join(f"{k} = {v}" for k, v in self._get(("voice", "apps")).items()))

        def read_apps():
            apps = {}
            for line in tb.get("1.0", "end").splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() and v.strip():
                        apps[k.strip().lower()] = v.strip()
            self._set(("voice", "apps"), apps)
        self._getters.append(read_apps)

        self._section(p, "Things you can say")
        ref = ctk.CTkTextbox(p, height=260, fg_color=theme.CARD_ALT, font=ctk.CTkFont(family="Consolas", size=12))
        ref.pack(fill="x", padx=4, pady=4)
        ref.insert("1.0", HELP_TEXT)
        ref.configure(state="disabled")

    def _tab_dictation(self, p) -> None:
        self._section(p, "Voice typing")
        self._button(p, "Dictation", "Speech is typed into whatever text box is active. Click the text box first.",
                     "Start dictation now", lambda: self._start_dictation())
        self._note(p, "To finish, say the stop phrase below (or choose another mode on the dashboard). "
                      "Say “scratch that” to delete the last phrase.")
        self._entry(p, "Stop phrase", "Say this to leave Dictation Mode.", ("dictation", "stop_phrase"))
        self._switch(p, "Spoken punctuation", "Say “comma”, “period”, “question mark”, “new line”... to type them.",
                     ("dictation", "punctuation_commands"))
        self._switch(p, "Capitalise sentences", "Start each sentence with a capital letter.", ("dictation", "auto_capitalize"))

        self._section(p, "Speech recognition (used for commands and dictation)")
        self._option(p, "Engine", "Offline (Vosk) stays on your computer. Google is free but sends your audio over the internet.",
                     ("speech", "engine"), [("vosk", "Offline (Vosk) - private"), ("google", "Google (online)")])
        self._option(p, "Language", "The language you speak. Offline mode also needs a matching model below.",
                     ("speech", "language"), LANGUAGES)
        models = list_models()
        cur = self._get(("speech", "vosk_model"))
        choices = [(m, m) for m in models]
        if cur not in models:
            choices.insert(0, (cur, f"{cur} (not installed)"))
        self._widgets["model"] = self._option(p, "Offline model", "Which downloaded model to use.", ("speech", "vosk_model"), choices)
        self.dl_button = self._button(p, "Get an offline model", "Downloads a small model (about 40 MB) for the language above. "
                                      "Needs internet once.", "Download model", self.c.download_model_for_language)
        self.dl_bar = ctk.CTkProgressBar(p)
        self.dl_bar.set(0)
        self.dl_label = ctk.CTkLabel(p, text="", font=ctk.CTkFont(size=11), text_color=theme.MUTED, anchor="w")
        self.dl_label.pack(fill="x", padx=8)

    def _tab_browser(self, p) -> None:
        self._section(p, "Browser control")
        self._switch(p, "Browser control", "Voice commands for tabs, search and navigation in your normal browser.",
                     ("browser", "enabled"))
        h = self._row(p, "Connection", "Handsfree uses your default browser and its keyboard shortcuts - no extension needed.")
        self.browser_status = ctk.CTkLabel(h, text="-", font=ctk.CTkFont(size=12, weight="bold"), text_color=theme.MUTED)
        self.browser_status.pack()
        self._option(p, "Search engine", "Used for “search for ...”.", ("browser", "search_engine"),
                     [(e, e.capitalize()) for e in SEARCH_ENGINES])
        self._entry(p, "Home page", "Opened by “open browser” and “home page”. Must start with https://",
                    ("browser", "home_page"), width=260)
        self._section(p, "Safety")
        self._switch(p, "Ask before risky actions", "Closing a tab or window, and opening a website by voice, "
                     "will wait for you to say “yes” or press Yes.", ("browser", "confirm_risky"))

    # ------------------------------------------------------------ actions
    def _start_dictation(self) -> None:
        self.c.set_mode(Mode.DICTATION)
        self.msg.configure(text="Dictation requested - check the dashboard." if self.c.modes.mode == Mode.DICTATION
                           else "Turn on Voice control, press Start, then try again.")

    def _update_area_label(self) -> None:
        a = self.c.cfg["cursor"]["area"]
        self.area_label.configure(
            text=f"Current area:  left {a['left']:.0%}  ·  right {a['right']:.0%}  ·  top {a['top']:.0%}  ·  bottom {a['bottom']:.0%}")
        self._set(("cursor", "area"), copy.deepcopy(a))
        self.baseline["cursor"]["area"] = copy.deepcopy(a)

    def _calibrate(self) -> None:
        if self.c.state == "stopped" or not self.c.gestures.running:
            self.msg.configure(text="Press Start on the dashboard first, then calibrate.")
            return
        self.c.start_calibration()
        if self.c.calibrator.active:
            self._calib_hidden = True
            self.withdraw()            # get out of the way so you can see the camera

    def _reset_area(self) -> None:
        self.c.reset_area()
        self._update_area_label()
        self.msg.configure(text="Tracking area reset.")

    def _refresh_cameras(self) -> None:
        self.msg.configure(text="Looking for cameras...")
        skip = (self.c.gestures.camera_index_in_use,) if self.c.gestures.camera_index_in_use is not None else ()

        def work():
            from gestures.camera import list_cameras
            try:
                self._cam_result = list_cameras(5, skip)
            except Exception:
                self._cam_result = []
        threading.Thread(target=work, daemon=True).start()

    def _reset(self) -> None:
        self.draft = ConfigManager.defaults()
        self._build()
        self.msg.configure(text="Defaults loaded - press “Save & apply” to keep them.")

    def _save(self) -> None:
        for g in self._getters:
            g()
        target = copy.deepcopy(self.c.cfg)             # keep changes made elsewhere (e.g. dashboard switches)
        _diff_apply(self.baseline, self.draft, target)
        cfg, warnings = self.c.apply_config(target)
        self.baseline = copy.deepcopy(cfg)
        self.draft = copy.deepcopy(cfg)
        if warnings:
            self.msg.configure(text="Saved, but some values were invalid and reset: " + " ".join(warnings[:2]),
                               text_color=theme.WARN)
        else:
            self.msg.configure(text="✓ Saved and applied", text_color=theme.GOOD)
        if self.on_saved:
            self.on_saved(cfg)

    # ------------------------------------------------------------ live updates
    def _poll(self) -> None:
        try:
            if not self.winfo_exists():
                return
            c = self.c
            if self._calib_hidden and not c.calibrator.active:
                self._calib_hidden = False
                self.deiconify()
                self._update_area_label()
                self.msg.configure(text="Calibration finished.", text_color=theme.GOOD)
                self.lift()
            feat = c.status.snapshot()["features"]
            st, detail = feat["browser"]
            self.browser_status.configure(
                text={"running": "● Ready", "error": "● Problem", "off": "● Off"}.get(st, "● Not running"),
                text_color={"running": theme.GOOD, "error": theme.BAD}.get(st, theme.MUTED))
            md = c.model_download
            if md["active"] or md["message"]:
                if md["active"] and not self.dl_bar.winfo_ismapped():
                    self.dl_bar.pack(fill="x", padx=8, pady=2, before=self.dl_label)
                self.dl_bar.set(md["progress"])
                self.dl_label.configure(text=md["message"])
            if md["done_name"] and md["done_name"] != self._seen_model:
                self._seen_model = md["done_name"]
                menu = self._widgets.get("model")
                if menu is not None:
                    names = list_models()
                    menu.configure(values=names)
                    menu.set(md["done_name"])
                self._set(("speech", "vosk_model"), md["done_name"])
                self.baseline["speech"]["vosk_model"] = md["done_name"]
            if self._cam_result is not None:
                found, self._cam_result = self._cam_result, None
                menu = self._widgets.get("camera")
                if menu is not None:
                    cur = self._get(("camera", "index"))
                    ids = sorted(set(found) | {cur})
                    menu.configure(values=[f"Camera {i}" for i in ids])
                    menu.set(f"Camera {cur}")
                    menu.configure(command=lambda l: self._set(("camera", "index"), int(l.split()[-1])))
                self.msg.configure(text=f"Found {len(found)} camera(s)." if found else "No cameras found.")
        except Exception:
            pass
        self._after_id = self.after(400, self._poll)
