"""Microphone discovery."""
from __future__ import annotations


def _input_devices() -> list[tuple[int, str]]:
    import pyaudio
    pa = pyaudio.PyAudio()
    try:
        devices = []
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0:
                devices.append((i, str(info["name"])))
        return devices
    finally:
        pa.terminate()


def list_microphones() -> list[str]:
    """Names of input devices (duplicates removed). Empty list if PyAudio is missing."""
    try:
        names = [n for _, n in _input_devices()]
    except Exception:
        try:
            import speech_recognition as sr
            names = list(sr.Microphone.list_microphone_names())
        except Exception:
            names = []
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def resolve_index(name: str):
    """Device index for a saved microphone name, or None for the system default."""
    if not name:
        return None
    try:
        for i, n in _input_devices():
            if n == name:
                return i
    except Exception:
        pass
    return None
