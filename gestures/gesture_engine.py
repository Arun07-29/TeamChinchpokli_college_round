"""Camera + MediaPipe loop. Runs in its own thread and routes each frame to the
cursor controller, scroll controller or calibrator depending on the current mode."""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from gestures import poses
from gestures.camera import RESOLUTIONS, open_camera
from gestures.cursor_controller import FINGER_TIPS, CursorController
from gestures.pointer_glide import PointerGlide
from gestures.scroll_controller import ScrollController, TwoFingerScroll

PREVIEW_MAX_W = 960                       # preview is drawn at most this wide (sharp in the big view)


class GestureEngine:
    def __init__(self, get_cfg: Callable[[], dict], actions, modes, status, log,
                 is_paused: Callable[[], bool], calibrator, on_fatal: Optional[Callable[[str], None]] = None):
        self.get_cfg = get_cfg
        self.actions = actions
        self.modes = modes
        self.status = status
        self.log = log
        self.is_paused = is_paused
        self.calibrator = calibrator
        self.on_fatal = on_fatal
        self.glide = PointerGlide(actions)
        self.cursor = CursorController(actions, self.glide)
        self.scroll = ScrollController(actions)
        self.two = TwoFingerScroll(actions)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._frame = None
        self._frame_id = 0
        self._flock = threading.Lock()
        self.camera_index_in_use: Optional[int] = None
        self.preview_wanted = True        # dashboard sets False while minimised (saves CPU)
        self.fps = 0.0
        self.resolution = (0, 0)

    # ---- lifecycle -------------------------------------------------
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="gesture-engine", daemon=True)
        self._thread.start()

    def request_stop(self) -> None:
        self._stop.set()

    def stop(self, timeout: float = 4.0) -> None:
        self._stop.set()
        t = self._thread
        if t and t is not threading.current_thread():
            t.join(timeout)

    def get_frame(self):
        with self._flock:
            return self._frame_id, self._frame

    def _set_frame(self, rgb) -> None:
        with self._flock:
            self._frame = rgb
            self._frame_id += 1

    # ---- main loop -------------------------------------------------
    def _run(self) -> None:
        st = self.status
        try:
            import cv2
            import mediapipe as mp
        except Exception as exc:
            st.set("webcam", "error", "OpenCV is not installed")
            st.set("hand_tracking", "error", f"Missing package: {exc.name if hasattr(exc, 'name') else exc}")
            self.log.error(f"Gesture engine can't start - missing package ({exc}). Run: pip install -r requirements.txt")
            return

        cfg = self.get_cfg()
        index = cfg["camera"]["index"]
        st.set("webcam", "starting", f"Opening camera {index}...")
        st.set("hand_tracking", "starting", "Loading hand model...")
        width, height = RESOLUTIONS.get(cfg["camera"].get("resolution", "720p"), (1280, 720))
        cap = open_camera(index, width, height)
        if cap is None:
            msg = f"Could not open camera {index}. Close other apps using it and check Windows camera privacy settings."
            st.set("webcam", "error", f"Camera {index} unavailable")
            st.set("hand_tracking", "stopped", "")
            st.set("cursor", "stopped"); st.set("scrolling", "stopped")
            self.log.error(msg)
            if self.on_fatal:
                self.on_fatal(msg)
            return
        self.camera_index_in_use = index
        self.resolution = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        if self.resolution[1]:
            poses.ASPECT = self.resolution[0] / self.resolution[1]
        st.set("webcam", "running", f"Camera {index} · {self.resolution[0]}x{self.resolution[1]}")

        hands = None
        mp_hands = mp_draw = None
        try:
            mp_hands = mp.solutions.hands
            mp_draw = mp.solutions.drawing_utils
            complexity = 0 if cfg["gestures"].get("model") == "fast" else 1
            hands = mp_hands.Hands(static_image_mode=False, max_num_hands=1, model_complexity=complexity,
                                   min_detection_confidence=0.6, min_tracking_confidence=0.5)
        except AttributeError:
            msg = "This MediaPipe version has no 'solutions' API. Install the pinned version: pip install mediapipe==0.10.21"
            st.set("hand_tracking", "error", "Wrong MediaPipe version")
            self.log.error(msg)
            cap.release()
            self.camera_index_in_use = None
            st.set("webcam", "stopped", "")
            return
        except Exception as exc:
            st.set("hand_tracking", "error", f"Could not start: {str(exc)[:60]}")
            self.log.error(f"Hand tracking could not start: {exc}")
            cap.release()
            self.camera_index_in_use = None
            st.set("webcam", "stopped", "")
            return
        st.set("hand_tracking", "running", "Looking for your hand")
        self.log.info(f"Camera {index} is on ({self.resolution[0]}x{self.resolution[1]}).")
        self.glide.start()
        last_mode = None
        failures = 0
        fps_t, fps_n = time.time(), 0
        try:
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    failures += 1
                    if failures > 30:
                        st.set("webcam", "error", "Camera stopped sending video")
                        self.log.error("The camera stopped sending frames (unplugged or taken by another app).")
                        if self.on_fatal:
                            self.on_fatal("Camera lost")
                        break
                    time.sleep(0.02)
                    continue
                failures = 0
                cfg = self.get_cfg()
                now = time.time()
                fps_n += 1
                if now - fps_t >= 1.0:
                    self.fps = fps_n / (now - fps_t)
                    fps_t, fps_n = now, 0
                    st.set("webcam", "running", f"Camera {index} · {self.resolution[0]}x{self.resolution[1]} · "
                                                f"{self.fps:.0f} fps")
                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                result = hands.process(rgb)
                lm = result.multi_hand_landmarks[0] if result.multi_hand_landmarks else None
                landmarks = lm.landmark if lm else None

                mode = self.modes.mode
                paused = self.is_paused()
                if mode != last_mode:
                    self.cursor.reset()
                    self.scroll.reset()
                    self.two.reset()
                    last_mode = mode

                info: dict = {}
                st.set("hand_tracking", "running", "Hand detected" if lm else "No hand in view")

                if self.calibrator.active:
                    self.calibrator.update((landmarks[8].x, landmarks[8].y) if lm else None, now)
                    st.set("cursor", "paused", "Calibrating")
                    st.set("scrolling", "paused", "Calibrating")
                elif paused:
                    st.set("cursor", "paused", "App is paused")
                    st.set("scrolling", "paused", "App is paused")
                    self.cursor.hand_lost()
                    self.two.reset()
                else:
                    cursor_ok, scroll_ok = self.modes.cursor_allowed(), self.modes.scroll_allowed()
                    if cursor_ok:
                        if self.cursor.fist:
                            st.set("cursor", "paused", "Fist - pointer held still")
                        elif self.cursor.dragging:
                            st.set("cursor", "running", "Dragging - open your fingers to drop")
                        else:
                            st.set("cursor", "running",
                                   "Pinch clicking ON" if cfg["click"]["enabled"] else "Pinch clicking OFF")
                    else:
                        st.set("cursor", "paused", f"Paused in {mode.value}")
                    two_ok = cursor_ok and cfg["scroll"]["two_finger"]
                    if scroll_ok:
                        st.set("scrolling", "running", "Scroll Mode: move your palm up/down")
                    elif two_ok and self.two.active:
                        st.set("scrolling", "running", "Two-finger scroll active")
                    elif two_ok:
                        st.set("scrolling", "idle", "Raise index + middle finger to scroll")
                    else:
                        st.set("scrolling", "idle", "Press S for Scroll Mode")
                    if lm is None:
                        self.cursor.hand_lost()
                        self.scroll.hand_lost()
                        self.two.reset()
                    elif scroll_ok:
                        info = self.scroll.update(landmarks, now, cfg)
                    elif cursor_ok:
                        if two_ok:
                            active, seen, tinfo = self.two.update(landmarks, now, cfg)
                        else:
                            active = seen = False
                            tinfo = {}
                        if active or seen:
                            self.cursor.suspend()          # pointer stays put while you scroll
                            info = tinfo
                        else:
                            info = self.cursor.update(landmarks, now, cfg)

                if (cfg["general"]["show_preview"] and self.preview_wanted) or self.calibrator.active:
                    self._set_frame(self._draw(cv2, mp_draw, mp_hands, frame, lm, cfg, mode, paused, info))
        except Exception as exc:
            from core.actions import pyautogui as _pg
            if _pg is not None and isinstance(exc, _pg.FailSafeException):
                self.log.error("Failsafe triggered (mouse in top-left corner).")
            else:
                self.log.error(f"Gesture engine crashed: {exc}")
                st.set("hand_tracking", "error", str(exc)[:80])
            if self.on_fatal:
                self.on_fatal(str(exc))
        finally:
            self.glide.stop()
            try:
                self.cursor.release()               # never leave the mouse button held down
            except Exception:
                pass
            try:
                hands.close()
            except Exception:
                pass
            cap.release()
            self.camera_index_in_use = None
            self._set_frame(None)
            for key in ("webcam", "hand_tracking", "cursor", "scrolling"):
                snap = st.snapshot()["features"][key][0]
                if snap != "error":
                    st.set(key, "stopped", "")
            self.log.info("Camera released.")

    # ---- preview ---------------------------------------------------
    def _draw(self, cv2, mp_draw, mp_hands, frame, lm, cfg, mode, paused, info):
        fh, fw = frame.shape[:2]
        img = cv2.resize(frame, (PREVIEW_MAX_W, int(fh * PREVIEW_MAX_W / fw))) if fw > PREVIEW_MAX_W else frame.copy()
        h, w = img.shape[:2]
        a = cfg["cursor"]["area"]
        cv2.rectangle(img, (int(a["left"] * w), int(a["top"] * h)),
                      (int(a["right"] * w), int(a["bottom"] * h)), (255, 190, 60), 1)
        if lm is not None:
            mp_draw.draw_landmarks(img, lm, mp_hands.HAND_CONNECTIONS)
            if info and "anchor" in info:
                ay = int(info["anchor"] * h)
                cv2.line(img, (0, ay), (w, ay), (0, 255, 255), 1)
                px, py = info["palm"]
                col = (0, 255, 0) if info["scrolling"] else (255, 255, 255)
                cv2.circle(img, (int(px * w), int(py * h)), 14, col, -1)
            elif info.get("active"):
                tip = lm.landmark[FINGER_TIPS[info["active"]]]
                col = (0, 140, 255) if info.get("drag") else (0, 255, 0)
                cv2.circle(img, (int(tip.x * w), int(tip.y * h)), 20, col, 3)
            if info.get("dwell"):
                tip = lm.landmark[8]
                cv2.ellipse(img, (int(tip.x * w), int(tip.y * h)), (26, 26), -90, 0,
                            int(360 * info["dwell"]), (0, 220, 255), 3)
            if "ratio" in info and cfg["click"]["enabled"]:       # pinch meter: fills as fingers close
                fill = min(1.0, max(0.0, 1.0 - (info["ratio"] - info["thr"]) / (info["thr"] * 2)))
                cv2.rectangle(img, (w - 30, 50), (w - 14, 200), (90, 90, 90), 1)
                cv2.rectangle(img, (w - 29, 200 - int(149 * fill)), (w - 15, 199),
                              (0, 255, 0) if info["ratio"] < info["thr"] else (200, 200, 200), -1)
        if paused:
            label = "PAUSED"
        elif info.get("two"):
            label = "TWO-FINGER SCROLL"
        elif info.get("fist"):
            label = "FIST - POINTER HELD"
        elif info.get("drag"):
            label = "DRAGGING"
        else:
            label = mode.value
        cv2.putText(img, label, (14, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        cv2.putText(img, f"{self.fps:.0f} fps", (w - 100, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
        if self.calibrator.active:
            cv2.putText(img, "CALIBRATING", (14, h - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 200, 255), 2)
        elif lm is None:
            cv2.putText(img, "Show one hand to the camera", (14, h - 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
