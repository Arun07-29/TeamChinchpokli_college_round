"""Microphone -> text. Uses SpeechRecognition for capture, then either Vosk (offline,
default) or Google's free web recogniser. Calls ``on_text(text)`` for every phrase."""
from __future__ import annotations

import json
import threading
import time
from typing import Callable, Optional

from voice.microphones import resolve_index
from voice.model_manager import model_path


class SpeechEngine:
    def __init__(self, get_cfg: Callable[[], dict], status, log, on_text: Callable[[str], None]):
        self.get_cfg = get_cfg
        self.status = status
        self.log = log
        self.on_text = on_text
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._model = None
        self._net_error_logged = 0.0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="speech-engine", daemon=True)
        self._thread.start()

    def request_stop(self) -> None:
        self._stop.set()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        t = self._thread
        if t and t is not threading.current_thread():
            t.join(timeout)

    # ------------------------------------------------------------------
    def _fail(self, voice_msg: str, mic_msg: str = "") -> None:
        self.status.set("voice", "error", voice_msg)
        self.status.set("microphone", "error" if mic_msg else "stopped", mic_msg)
        self.log.error(voice_msg + (f" ({mic_msg})" if mic_msg else ""))

    def _run(self) -> None:
        st = self.status
        cfg = self.get_cfg()
        st.set("voice", "starting", "Preparing speech recognition...")
        st.set("microphone", "starting", "Opening microphone...")
        try:
            import speech_recognition as sr
        except ImportError:
            return self._fail("Missing package 'SpeechRecognition'", "pip install SpeechRecognition PyAudio")

        self._model = None
        if cfg["speech"]["engine"] == "vosk":
            path = model_path(cfg["speech"]["vosk_model"])
            if not path.exists():
                return self._fail("Offline speech model not found",
                                  "Settings > Dictation > Download model (or switch engine to Google)")
            try:
                from vosk import Model, SetLogLevel
                SetLogLevel(-1)
                st.set("voice", "starting", "Loading offline model...")
                self._model = Model(str(path))
            except ImportError:
                return self._fail("Missing package 'vosk'", "pip install vosk")
            except Exception as exc:
                return self._fail(f"Could not load offline model: {exc}")

        try:
            mic = sr.Microphone(device_index=resolve_index(cfg["voice"]["microphone"]))
            recognizer = sr.Recognizer()
            with mic as source:
                if cfg["voice"]["energy_threshold"] > 0:
                    recognizer.dynamic_energy_threshold = False
                    recognizer.energy_threshold = cfg["voice"]["energy_threshold"]
                else:
                    st.set("microphone", "starting", "Measuring background noise...")
                    recognizer.adjust_for_ambient_noise(source, duration=1.0)
        except Exception as exc:
            return self._fail("Microphone unavailable",
                              f"{exc}" if str(exc) else "Check Windows microphone privacy settings and PyAudio")
        recognizer.pause_threshold = 0.8
        if self._stop.is_set():
            return

        stopper = recognizer.listen_in_background(
            mic, lambda r, a: self._on_audio(sr, r, a), phrase_time_limit=12)
        st.set("voice", "running", "Waiting for a command")
        st.set("microphone", "running", "Listening")
        self.log.info("Voice control is on.")
        try:
            while not self._stop.wait(0.25):
                pass
        finally:
            try:
                stopper(wait_for_stop=True)
            except Exception:
                pass
            self._model = None
            for key in ("voice", "microphone"):
                if st.snapshot()["features"][key][0] != "error":
                    st.set(key, "stopped", "")
            self.log.info("Microphone released.")

    # ------------------------------------------------------------------
    def _on_audio(self, sr, recognizer, audio) -> None:
        if self._stop.is_set():
            return
        try:
            self.status.set("microphone", "running", "Recognising...")
            text = self._transcribe(sr, recognizer, audio)
            if self.status.snapshot()["features"]["voice"][0] == "error":
                self.status.set("voice", "running", "Waiting for a command")
            if text:
                self.on_text(text)
        except sr.UnknownValueError:
            pass
        except sr.RequestError as exc:
            self.status.set("voice", "error", "Google speech service unreachable")
            if time.time() - self._net_error_logged > 30:
                self._net_error_logged = time.time()
                self.log.error(f"Speech service error: {exc}. Check your internet or switch to the offline engine.")
        except Exception as exc:
            self.log.error(f"Speech recognition error: {exc}")
        finally:
            if not self._stop.is_set():
                self.status.set("microphone", "running", "Listening")

    def _transcribe(self, sr, recognizer, audio) -> str:
        cfg = self.get_cfg()
        if cfg["speech"]["engine"] == "google":
            return recognizer.recognize_google(audio, language=cfg["speech"]["language"])
        from vosk import KaldiRecognizer
        rec = KaldiRecognizer(self._model, 16000)
        rec.AcceptWaveform(audio.get_raw_data(convert_rate=16000, convert_width=2))
        return json.loads(rec.FinalResult()).get("text", "").strip()
