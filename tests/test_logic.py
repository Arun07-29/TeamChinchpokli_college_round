"""Run with:  python -m unittest discover -s tests -v   (no camera, mic or screen needed)"""
import copy
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config_manager import ConfigManager, DEFAULTS, validate_config
from core.confirmation import ConfirmationManager
from core.mode_manager import Mode, ModeManager
from core.status import ActivityLog
from gestures.cursor_controller import CursorController
from gestures.scroll_controller import ScrollController, TwoFingerScroll, two_finger_pose
from voice.commands import normalize, normalize_site, parse_command, parse_commands, strip_wake_phrase
from voice.dictation import DictationFormatter


class FakeActions:
    def __init__(self):
        self.calls = []
    def screen_size(self): return (1000, 800)
    def position(self): return (500, 400)
    def move(self, x, y): self.calls.append(("move", x, y))
    def click(self): self.calls.append(("click",))
    def right_click(self): self.calls.append(("right",))
    def double_click(self): self.calls.append(("double",))
    def mouse_down(self): self.calls.append(("down",))
    def mouse_up(self): self.calls.append(("up",))
    def scroll(self, n): self.calls.append(("scroll", n))
    def kinds(self): return [c[0] for c in self.calls]
    def buttons(self): return [c[0] for c in self.calls if c[0] != "move"]


def hand(index=(0.5, 0.5), palm_y=0.5):
    """Flat fake hand (all palm points at palm_y) - used by the scroll tests."""
    pts = [SimpleNamespace(x=0.5, y=palm_y) for _ in range(21)]
    pts[4] = SimpleNamespace(x=0.3, y=0.3)
    pts[8] = SimpleNamespace(x=index[0], y=index[1])
    for i in (12, 16, 20):
        pts[i] = SimpleNamespace(x=0.8, y=0.9)
    return pts


def real_hand(index=(0.45, 0.40), pinch=None, fist=False):
    """Anatomically plausible hand (palm size ~0.26). ``pinch`` moves the THUMB onto that fingertip."""
    P = SimpleNamespace
    pts = [P(x=0.5, y=0.7) for _ in range(21)]
    pts[0] = P(x=0.5, y=0.9)                                        # wrist
    for (mcp, pip, tip), x in zip(((5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20)), (0.45, 0.5, 0.55, 0.6)):
        pts[mcp], pts[pip] = P(x=x, y=0.65), P(x=x, y=0.55)
        pts[tip] = P(x=x, y=0.68) if fist else P(x=x, y=0.42)
    if not fist:
        pts[8] = P(x=index[0], y=index[1])
    pts[4] = P(x=0.47, y=0.62) if fist else P(x=0.30, y=0.62)     # thumb tip
    if pinch:
        tip = pts[{"index": 8, "middle": 12, "ring": 16, "pinky": 20}[pinch]]
        pts[4] = P(x=tip.x + 0.01, y=tip.y + 0.01)
    return pts


class ConfigTests(unittest.TestCase):
    def test_defaults_are_valid_and_safe(self):
        cfg, warnings = validate_config(copy.deepcopy(DEFAULTS))
        self.assertEqual(warnings, [])
        self.assertFalse(cfg["click"]["enabled"])
        self.assertFalse(cfg["voice"]["enabled"])

    def test_bad_values_fall_back(self):
        cfg, w = validate_config({"cursor": {"speed": 99, "smoothing": "x"}, "click": {"enabled": "yes"},
                                  "voice": {"activation": "shout"}, "general": 5})
        self.assertEqual(cfg["cursor"]["speed"], DEFAULTS["cursor"]["speed"])
        self.assertEqual(cfg["cursor"]["smoothing"], DEFAULTS["cursor"]["smoothing"])
        self.assertFalse(cfg["click"]["enabled"])
        self.assertEqual(cfg["voice"]["activation"], "wake_phrase")
        self.assertTrue(len(w) >= 4)

    def test_missing_keys_filled(self):
        cfg, _ = validate_config({"scroll": {"sensitivity": 2.0}})
        self.assertEqual(cfg["scroll"]["sensitivity"], 2.0)
        self.assertEqual(cfg["scroll"]["deadzone"], DEFAULTS["scroll"]["deadzone"])

    def test_gesture_conflict_resolved(self):
        cfg, w = validate_config({"click": {"right_click_gesture": "thumb_ring", "double_click_gesture": "thumb_ring"}})
        self.assertEqual(cfg["click"]["double_click_gesture"], "off")
        self.assertTrue(w)

    def test_bad_area_rejected(self):
        cfg, w = validate_config({"cursor": {"area": {"left": 0.5, "right": 0.55, "top": 0.1, "bottom": 0.9}}})
        self.assertEqual(cfg["cursor"]["area"], DEFAULTS["cursor"]["area"])

    def test_apps_cleaned(self):
        cfg, _ = validate_config({"version": 2, "voice": {"apps": {"  Notepad ": "notepad.exe", "": "x", "bad": 5}}})
        self.assertEqual(cfg["voice"]["apps"], {"notepad": "notepad.exe"})

    def test_v1_config_migrates(self):
        old = {"version": 1, "click": {"pinch_threshold": 0.045, "enabled": True},
               "voice": {"apps": {"notepad": "my-notepad.exe"}}}
        cfg, w = validate_config(old)
        self.assertEqual(w, [])
        self.assertTrue(cfg["click"]["enabled"])
        self.assertEqual(cfg["click"]["pinch_ratio"], DEFAULTS["click"]["pinch_ratio"])
        self.assertEqual(cfg["voice"]["apps"]["notepad"], "my-notepad.exe")      # user's entry kept
        self.assertEqual(len(cfg["voice"]["apps"]), len(DEFAULTS["voice"]["apps"]))

    def test_save_load_roundtrip_and_corrupt_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            cm = ConfigManager(p)
            cfg = copy.deepcopy(cm.config)
            cfg["scroll"]["sensitivity"] = 2.5
            self.assertTrue(cm.save(cfg))
            self.assertEqual(ConfigManager(p).config["scroll"]["sensitivity"], 2.5)
            p.write_text("{ not json")
            cm2 = ConfigManager(p)
            self.assertTrue(cm2.warnings)
            self.assertEqual(cm2.config["scroll"]["sensitivity"], DEFAULTS["scroll"]["sensitivity"])
            self.assertTrue(list(Path(d).glob("config.corrupt-*.json")))
            json.loads(p.read_text())          # rewritten as valid JSON


class ModeTests(unittest.TestCase):
    def test_scroll_toggle_and_permissions(self):
        m = ModeManager()
        self.assertTrue(m.cursor_allowed() and not m.scroll_allowed())
        m.toggle_scroll()
        self.assertTrue(m.scroll_allowed() and not m.cursor_allowed())
        m.toggle_scroll()
        self.assertEqual(m.mode, Mode.CURSOR)

    def test_dictation_returns_to_previous_mode(self):
        m = ModeManager()
        m.set(Mode.SCROLL); m.set(Mode.DICTATION)
        self.assertTrue(m.cursor_allowed())
        m.leave_dictation()
        self.assertEqual(m.mode, Mode.SCROLL)

    def test_voice_mode_pauses_hands(self):
        m = ModeManager(); m.set(Mode.VOICE)
        self.assertFalse(m.cursor_allowed() or m.scroll_allowed())


class CursorTests(unittest.TestCase):
    def setUp(self):
        self.a = FakeActions()
        self.cur = CursorController(self.a)
        self.cfg = copy.deepcopy(DEFAULTS)
        self.cfg["click"]["enabled"] = True

    def feed(self, frames, t0=100.0, dt=1 / 30):
        """Feed hands at 30 fps; returns the time after the last frame."""
        t = t0
        for h in frames:
            self.cur.update(h, t, self.cfg)
            t += dt
        return t

    def test_pointer_moves_without_click_when_disabled(self):
        self.cfg["click"]["enabled"] = False
        self.feed([real_hand((0.8, 0.8))] * 3 + [real_hand((0.8, 0.8), pinch="index")] * 4 + [real_hand((0.8, 0.8))] * 3)
        self.assertEqual(self.a.buttons(), [])
        self.assertIn("move", self.a.kinds())

    def test_quick_pinch_is_a_click_down_then_up(self):
        self.feed([real_hand()] * 3 + [real_hand(pinch="index")] * 3 + [real_hand()] * 2)
        self.assertEqual(self.a.buttons(), ["down", "up"])

    def test_single_frame_glitch_does_not_click(self):
        self.feed([real_hand()] * 3 + [real_hand(pinch="index")] + [real_hand()] * 3)
        self.assertEqual(self.a.buttons(), [])

    def test_held_pinch_does_not_repeat_and_cooldown_applies(self):
        self.cfg["click"]["drag_enabled"] = False
        t = self.feed([real_hand()] * 2 + [real_hand(pinch="index")] * 6)
        self.assertEqual(self.a.buttons(), ["click"])                       # held: no repeat
        t = self.feed([real_hand()] * 2 + [real_hand(pinch="index")] * 3, t0=t)
        self.assertEqual(self.a.buttons(), ["click"])                       # inside cooldown
        self.feed([real_hand()] * 2 + [real_hand(pinch="index")] * 3, t0=t + 1.0)
        self.assertEqual(self.a.buttons(), ["click", "click"])

    def test_pinch_and_hold_drags_then_drops(self):
        t = self.feed([real_hand((0.45, 0.40))] * 3 + [real_hand((0.45, 0.40), pinch="index")] * 15)   # 0.5 s hold
        self.assertEqual(self.a.buttons(), ["down"])
        n_moves = self.a.kinds().count("move")
        t = self.feed([real_hand((0.70, 0.60), pinch="index")] * 5, t0=t)   # drag the hand while pinched
        self.assertGreater(self.a.kinds().count("move"), n_moves)
        self.feed([real_hand((0.70, 0.60))] * 3, t0=t)
        self.assertEqual(self.a.buttons(), ["down", "up"])

    def test_pointer_frozen_during_a_quick_click(self):
        t = self.feed([real_hand((0.5, 0.4))] * 5)
        t = self.feed([real_hand((0.5, 0.4), pinch="index")] * 2, t0=t)            # press registers
        n = len(self.a.calls)
        self.feed([real_hand((0.52, 0.42), pinch="index")], t0=t)                   # small wobble while pinched
        self.assertEqual(len(self.a.calls), n)

    def test_click_lands_where_pointer_was_before_the_pinch(self):
        self.cfg["click"]["drag_enabled"] = False
        self.cfg["cursor"]["smoothing"] = 0.0
        t = self.feed([real_hand((0.5, 0.4))] * 10)
        before = [c for c in self.a.calls if c[0] == "move"][-1]
        # fingers closing drags the fingertip a little before the pinch registers
        self.feed([real_hand((0.53, 0.43))] * 2 + [real_hand((0.53, 0.43), pinch="index")] * 2, t0=t)
        i = self.a.kinds().index("click")
        self.assertEqual(self.a.calls[i - 1], before)

    def test_right_and_double_click_gestures(self):
        t = self.feed([real_hand()] * 2 + [real_hand(pinch="middle")] * 3 + [real_hand()] * 2)
        self.feed([real_hand(pinch="ring")] * 3 + [real_hand()] * 2, t0=t + 1.0)
        self.assertEqual(self.a.buttons(), ["right", "double"])

    def test_fist_holds_pointer_and_never_clicks(self):
        self.feed([real_hand()] * 3)
        n = self.a.kinds().count("move")
        self.feed([real_hand(fist=True)] * 10)
        self.assertTrue(self.cur.fist)
        self.assertEqual(self.a.buttons(), [])
        self.assertLessEqual(self.a.kinds().count("move") - n, 3)           # only the frames before the fist locked

    def test_hand_lost_while_dragging_releases_button(self):
        self.feed([real_hand()] * 2 + [real_hand(pinch="index")] * 3)
        self.cur.hand_lost()
        self.assertEqual(self.a.buttons(), ["down", "up"])

    def test_dwell_click(self):
        self.cfg["click"]["dwell_enabled"] = True
        self.cfg["click"]["dwell_time"] = 0.5
        self.feed([real_hand((0.5, 0.4))] * 30)                              # 1 s of holding still
        self.assertEqual(self.a.buttons(), ["click"])                        # once, not repeatedly

    def test_never_lands_on_a_failsafe_corner(self):
        self.cfg["cursor"]["smoothing"] = 0.0
        self.feed([real_hand((0.0, 0.0))] * 10)
        x, y = [c for c in self.a.calls if c[0] == "move"][-1][1:]
        self.assertEqual((x, y), (1, 1))

    def test_calibrated_area_changes_mapping(self):
        self.cfg["cursor"]["smoothing"] = 0.0
        self.cfg["cursor"]["area"] = {"left": 0.0, "right": 0.5, "top": 0.0, "bottom": 0.5}
        self.feed([real_hand((0.5, 0.45))] * 5)
        last = [c for c in self.a.calls if c[0] == "move"][-1]
        self.assertGreater(last[1], 900)       # right edge of the area == right edge of the screen


class FilterTests(unittest.TestCase):
    def test_one_euro_smooths_jitter_but_follows_fast_moves(self):
        from gestures.poses import OneEuroFilter
        f = OneEuroFilter(min_cutoff=1.0, beta=8.0)
        out = [f(0.5 + (0.004 if i % 2 else -0.004), i / 30) for i in range(60)]
        self.assertLess(max(out[30:]) - min(out[30:]), 0.004)              # jitter shrinks a lot
        f.reset()
        out = [f(i * 0.05, i / 30) for i in range(20)]                     # fast sweep
        self.assertGreater(out[-1], 19 * 0.05 - 0.1)                       # small lag

    def test_pinch_ratio_is_scale_independent(self):
        from gestures.poses import pinch_ratios
        near = real_hand(pinch="index")
        far = [SimpleNamespace(x=0.5 + (p.x - 0.5) * 0.5, y=0.5 + (p.y - 0.5) * 0.5) for p in near]
        self.assertAlmostEqual(pinch_ratios(near)["index"], pinch_ratios(far)["index"], places=6)


class GlideTests(unittest.TestCase):
    def test_glide_moves_smoothly_at_high_rate_and_snaps_for_clicks(self):
        from gestures.pointer_glide import PointerGlide
        a = FakeActions(); g = PointerGlide(a)
        g.start()
        try:
            g.target(800, 400)                       # starts from the real pointer (500, 400)
            time.sleep(0.25)
            xs = [c[1] for c in a.calls if c[0] == "move"]
            self.assertGreater(len(xs), 5)           # many small steps, not one jump
            self.assertEqual(xs, sorted(xs))         # always moving toward the target
            self.assertEqual(xs[-1], 800)            # and arrives exactly
            g.snap(100, 100)
            self.assertEqual(a.calls[-1], ("move", 100, 100))
            n = len(a.calls); time.sleep(0.05)
            self.assertEqual(len(a.calls), n)        # at rest: no extra mouse events
        finally:
            g.stop()

    def test_cursor_uses_glide_when_enabled(self):
        class G:
            def __init__(self): self.t = []
            def target(self, x, y): self.t.append((x, y))
            def snap(self, x, y): self.t.append(("snap", x, y))
            def halt(self): pass
        a, g = FakeActions(), G()
        cur = CursorController(a, g); cfg = copy.deepcopy(DEFAULTS)
        for i in range(3):
            cur.update(real_hand((0.6, 0.4)), 1.0 + i / 30, cfg)
        self.assertTrue(g.t); self.assertNotIn("move", a.kinds())
        cfg["cursor"]["glide"] = False
        cur.update(real_hand((0.2, 0.2)), 1.2, cfg)
        self.assertIn("move", a.kinds())

    def test_widescreen_aspect_keeps_pinch_ratio_sane(self):
        from gestures import poses
        h = real_hand(pinch="index")
        try:
            poses.ASPECT = 16 / 9
            self.assertLess(poses.pinch_ratios(h)["index"], DEFAULTS["click"]["pinch_ratio"])
            self.assertGreater(poses.pinch_ratios(real_hand())["index"], DEFAULTS["click"]["pinch_ratio"] * 1.4)
        finally:
            poses.ASPECT = 1.0


class ScrollTests(unittest.TestCase):
    def test_scrolls_only_beyond_deadzone_and_never_clicks(self):
        a = FakeActions(); s = ScrollController(a); cfg = copy.deepcopy(DEFAULTS)
        s.update(hand(palm_y=0.5), 1.0, cfg)                       # sets the anchor
        s.update(hand(palm_y=0.51), 1.05, cfg)                     # inside dead zone
        self.assertEqual(a.calls, [])
        for i in range(5):
            s.update(hand(palm_y=0.30), 1.1 + i * 0.03, cfg)       # moved up
        self.assertTrue(a.calls and all(c[0] == "scroll" and c[1] > 0 for c in a.calls))
        a.calls.clear(); s.reset()
        s.update(hand(palm_y=0.5), 2.0, cfg)
        for i in range(5):
            s.update(hand(palm_y=0.8), 2.1 + i * 0.03, cfg)        # moved down
        self.assertTrue(a.calls and all(c[1] < 0 for c in a.calls))

    def test_invert(self):
        a = FakeActions(); s = ScrollController(a); cfg = copy.deepcopy(DEFAULTS); cfg["scroll"]["invert"] = True
        s.update(hand(palm_y=0.5), 1.0, cfg)
        for i in range(5):
            s.update(hand(palm_y=0.3), 1.1 + i * 0.03, cfg)
        self.assertTrue(all(c[1] < 0 for c in a.calls))


def two_finger_hand(y=0.3, ring_up=False, dy=0.0):
    P = lambda x, yy: SimpleNamespace(x=x, y=yy + dy)
    pts = [P(0.5, 0.6) for _ in range(21)]
    pts[0], pts[9] = P(0.5, 0.9), P(0.5, 0.6)
    pts[6], pts[8] = P(0.46, 0.5), P(0.46, y)            # index
    pts[10], pts[12] = P(0.5, 0.48), P(0.5, y - 0.02)    # middle
    pts[14], pts[16] = P(0.54, 0.55), P(0.54, 0.3 if ring_up else 0.63)   # ring
    pts[18], pts[20] = P(0.58, 0.58), P(0.58, 0.65)      # little finger folded
    return pts


class TwoFingerTests(unittest.TestCase):
    def test_pose_detection(self):
        self.assertTrue(two_finger_pose(two_finger_hand()))
        self.assertFalse(two_finger_pose(two_finger_hand(ring_up=True)))   # open hand
        self.assertFalse(two_finger_pose(hand()))

    def test_scrolls_up_and_down_and_pointer_is_ignored(self):
        a = FakeActions(); t = TwoFingerScroll(a); cfg = copy.deepcopy(DEFAULTS)
        for i in range(4):
            t.update(two_finger_hand(0.3), 1.0 + i * 0.03, cfg)
        self.assertTrue(t.active); self.assertEqual(a.calls, [])          # holding still: no scroll
        for i in range(5):
            t.update(two_finger_hand(dy=-0.2), 1.2 + i * 0.03, cfg)       # whole hand moved up
        self.assertTrue(a.calls and all(c[0] == "scroll" and c[1] > 0 for c in a.calls))
        a.calls.clear()
        for i in range(8):
            t.update(two_finger_hand(dy=0.1), 1.5 + i * 0.03, cfg)        # whole hand moved down
        self.assertTrue(a.calls and a.calls[-1][1] < 0 and sum(c[1] for c in a.calls) < 0)

    def test_exits_after_pose_lost(self):
        a = FakeActions(); t = TwoFingerScroll(a); cfg = copy.deepcopy(DEFAULTS)
        for i in range(4):
            t.update(two_finger_hand(), 1.0 + i * 0.03, cfg)
        for i in range(6):
            t.update(hand(), 1.2 + i * 0.03, cfg)
        self.assertFalse(t.active)


class VoiceTests(unittest.TestCase):
    def test_wake_phrase_is_forgiving(self):
        w = "hey handsfree"
        self.assertEqual(strip_wake_phrase("hey hans free click", w), "click")
        self.assertEqual(strip_wake_phrase("okay hey hands free scroll down", w), "scroll down")
        self.assertIsNone(strip_wake_phrase("scroll down", w))
        self.assertIsNone(strip_wake_phrase("hello there click", w))

    def test_wake_phrase_variants(self):
        self.assertEqual(strip_wake_phrase("hey hands free scroll up", "hey handsfree"), "scroll up")
        self.assertEqual(strip_wake_phrase("hey handsfree", "hey handsfree"), "")
        self.assertIsNone(strip_wake_phrase("scroll up", "hey handsfree"))

    def test_commands(self):
        p = lambda s: parse_command(normalize(s))
        self.assertEqual(p("Click.").name, "click")
        self.assertEqual(p("double click").name, "double_click")
        self.assertEqual(p("scroll down five").args, {"direction": "down", "notches": 5})
        self.assertEqual(p("scroll down 500").args["notches"], 20)
        self.assertEqual(p("scroll mode").args["mode"], "Scroll")
        self.assertEqual(p("press page down").args["key"], "pagedown")
        self.assertEqual(p("close tab").args["action"], "close_tab")
        self.assertEqual(p("open notepad").name, "open_app")
        self.assertEqual(p("open browser").args["action"], "open")
        self.assertEqual(p("search for cute cats").args["query"], "cute cats")
        self.assertIsNone(p("blah blah"))
        self.assertIsNone(p("scroll sideways"))

    def test_natural_phrasing_and_new_commands(self):
        p = lambda s: parse_command(normalize(s))
        self.assertEqual(p("Can you scroll down a bit please").args, {"direction": "down", "notches": 1})
        self.assertEqual(p("scroll down 5 times").args["notches"], 5)
        self.assertEqual(p("scroll right").args["direction"], "right")
        self.assertEqual(p("write click").name, "right_click")               # common misrecognition
        self.assertEqual(p("scroll dawn").args["direction"], "down")          # fuzzy near-miss
        self.assertEqual(p("press control shift t").args["keys"], ["ctrl", "shift", "t"])
        self.assertEqual(p("press down three times").args, {"key": "down", "presses": 3})
        self.assertEqual(p("copy").args["action"], "copy")
        self.assertEqual(p("volume up 10").args, {"key": "volumeup", "presses": 10})
        self.assertEqual(p("next song").args["key"], "nexttrack")
        self.assertEqual(p("minimize window").args["action"], "minimize")
        self.assertEqual(p("search youtube for lofi music").args, {"action": "youtube", "query": "lofi music"})
        self.assertEqual(p("play despacito on youtube").args["query"], "despacito")
        self.assertEqual(p("go to tab 3").args, {"action": "tab", "number": 3})
        self.assertEqual(p("move mouse left a bit").args, {"direction": "left", "pixels": 20})
        self.assertEqual(p("hold").name, "mouse_down")
        self.assertEqual(p("open youtube").name, "open_app")                  # router falls back to the website
        self.assertIsNone(p("press banana"))
        self.assertIsNone(p("close tap"))                                     # never guess risky commands

    def test_chained_commands(self):
        cmds = parse_commands(normalize("scroll down and click"))
        self.assertEqual([c.name for c in cmds], ["scroll", "click"])
        self.assertEqual(len(parse_commands(normalize("search for salt and pepper"))), 1)
        self.assertEqual(parse_commands(normalize("click and banana")), [])

    def test_site_names(self):
        self.assertEqual(normalize_site("youtube dot com"), "youtube.com")
        self.assertEqual(normalize_site("openai com"), "openai.com")
        self.assertEqual(normalize_site("youtube"), "")

    def test_dictation_formatting(self):
        d = DictationFormatter()
        self.assertEqual(d.format("hello world comma this is a test period"), "Hello world, this is a test.")
        self.assertEqual(d.format("it works question mark"), " It works?")
        self.assertEqual(d.format("new line next"), "\nNext")
        self.assertEqual(d.undo_length(), 5)
        d2 = DictationFormatter()
        self.assertEqual(d2.format("hello comma", punctuation=False, capitalize=False), "hello comma")


class ConfirmTests(unittest.TestCase):
    def test_yes_runs_no_cancels_timeout_expires(self):
        cm = ConfirmationManager(ActivityLog(), timeout=0.2)
        hits = []
        cm.request("Close tab?", lambda: hits.append(1)); cm.resolve(False)
        self.assertEqual(hits, [])
        cm.request("Close tab?", lambda: hits.append(1)); cm.resolve(True)
        self.assertEqual(hits, [1])
        cm.request("Close tab?", lambda: hits.append(1)); time.sleep(0.3)
        self.assertIsNone(cm.current()); cm.resolve(True)
        self.assertEqual(hits, [1])


class ControllerTests(unittest.TestCase):
    def make(self):
        from core.app_controller import AppController
        d = tempfile.mkdtemp()
        cm = ConfigManager(Path(d) / "config.json")
        cfg = copy.deepcopy(cm.config)
        cfg["gestures"]["enabled"] = False; cfg["voice"]["enabled"] = False
        cfg["hotkeys"]["enabled"] = False; cfg["browser"]["enabled"] = False
        cfg["voice"]["sounds"] = False
        cm.save(cfg)
        return AppController(ConfigManager(Path(d) / "config.json")), d

    def wait_stopped(self, c):
        for _ in range(50):
            if not c.stopping:
                return
            time.sleep(0.05)
        self.fail("never finished stopping")

    def test_lifecycle(self):
        c, _ = self.make()
        c.start(); self.assertEqual(c.state, "running")
        c.pause(); self.assertEqual(c.state, "paused")
        c.resume(); self.assertEqual(c.state, "running")
        c.stop(); self.assertEqual(c.state, "stopped"); self.wait_stopped(c)
        c.start(); self.assertEqual(c.state, "running")
        c.shutdown()

    def test_emergency_stop_disables_clicking(self):
        c, _ = self.make()
        c.update_setting("click.enabled", True); c.start()
        c.emergency_stop("test")
        self.assertEqual(c.state, "stopped"); self.assertFalse(c.cfg["click"]["enabled"])
        self.wait_stopped(c)

    def test_settings_persist_and_validate(self):
        c, d = self.make()
        c.update_setting("scroll.sensitivity", 2.2)
        self.assertEqual(json.loads((Path(d) / "config.json").read_text())["scroll"]["sensitivity"], 2.2)
        bad = copy.deepcopy(c.cfg); bad["scroll"]["sensitivity"] = 999
        clean, warnings = c.apply_config(bad)
        self.assertEqual(clean["scroll"]["sensitivity"], DEFAULTS["scroll"]["sensitivity"]); self.assertTrue(warnings)

    def fake_actions(self, c, **fns):
        base = dict(available=True, release_all=lambda: None)
        base.update(fns)
        c.actions = SimpleNamespace(**base)

    def test_voice_session_routes_commands(self):
        c, _ = self.make()
        calls = []
        self.fake_actions(c, click=lambda: calls.append("click"), scroll_notches=lambda n: calls.append(("scroll", n)))
        c.start()
        c.session.handle_text("click")                                  # no wake phrase -> ignored
        self.assertEqual(calls, [])
        c.session.handle_text("Hey handsfree scroll down two")
        self.assertEqual(calls, [("scroll", -2)])
        c.session.handle_text("click")                                  # inside listening window
        self.assertEqual(calls[-1], "click")
        c.pause(); c.session.handle_text("click")
        self.assertEqual(calls.count("click"), 1)                       # paused: ignored
        c.shutdown()

    def test_risky_browser_action_needs_yes(self):
        c, _ = self.make()
        c.update_setting("browser.enabled", True)
        done = []
        c.browser.perform = lambda action, **kw: done.append(action) or "ok"
        c.start(); c.browser.active = True      # (no default browser exists in the test sandbox)
        c.session.arm()
        c.session.handle_text("close tab")
        self.assertEqual(done, []); self.assertTrue(c.confirm.has_pending())
        c.session.handle_text("hey handsfree yes")                      # wake phrase + yes also works
        self.assertEqual(done, ["close_tab"])
        c.shutdown()

    def test_known_site_opens_without_asking(self):
        c, _ = self.make()
        c.update_setting("browser.enabled", True)
        done = []
        c.browser.perform = lambda action, **kw: done.append((action, kw)) or "ok"
        c.start(); c.browser.active = True
        c.session.handle_text("hey handsfree open youtube")
        self.assertEqual(done, [("go_to", {"target": "youtube"})]); self.assertFalse(c.confirm.has_pending())
        c.shutdown()

    def test_alternative_transcripts_rescue_a_command(self):
        c, _ = self.make()
        calls = []
        self.fake_actions(c, right_click=lambda: calls.append("right"))
        c.start()
        c.session.handle_text("hey handsfree bright clicks bye", ["hey handsfree right click"])
        self.assertEqual(calls, ["right"])
        c.shutdown()

    def test_type_keeps_original_case(self):
        c, _ = self.make()
        typed = []
        self.fake_actions(c, type_text=lambda t: typed.append(t))
        c.start()
        c.session.handle_text("Hey handsfree type Hello World")
        self.assertEqual(typed, ["Hello World"])
        c.shutdown()

    def test_dictation_stop_phrase_at_end_of_sentence(self):
        c, _ = self.make()
        typed = []
        self.fake_actions(c, type_text=lambda t: typed.append(t))
        c.speech._thread = SimpleNamespace(is_alive=lambda: True)          # pretend the mic is on
        c.start(); c.set_mode(Mode.DICTATION)
        self.assertEqual(c.modes.mode, Mode.DICTATION)
        c.session.handle_text("hello world stop dictation")
        self.assertEqual(typed, ["Hello world"])
        self.assertEqual(c.modes.mode, Mode.CURSOR)
        c.speech._thread = None
        c.shutdown()

    def test_background_chatter_stays_out_of_activity_log(self):
        c, _ = self.make()
        c.start()
        before = len(c.log.since(0))
        c.session.handle_text("koi bhi hai")
        self.assertEqual(len(c.log.since(0)), before)
        self.assertIn("first", c.status.snapshot()["info"]["last_heard"])
        c.shutdown()


if __name__ == "__main__":
    unittest.main()
