"""Offline (Vosk) speech models: find installed ones and download a small one."""
from __future__ import annotations

import shutil
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from config_manager import APP_DIR

MODELS_DIR = APP_DIR / "models"
BASE_URL = "https://alphacephei.com/vosk/models/{name}.zip"
LANG_MODELS = {
    "en-US": "vosk-model-small-en-us-0.15", "en-GB": "vosk-model-small-en-us-0.15",
    "en-IN": "vosk-model-small-en-in-0.4", "hi-IN": "vosk-model-small-hi-0.22",
    "es-ES": "vosk-model-small-es-0.42", "fr-FR": "vosk-model-small-fr-0.22",
    "de-DE": "vosk-model-small-de-0.15", "it-IT": "vosk-model-small-it-0.22",
    "pt-BR": "vosk-model-small-pt-0.3", "ja-JP": "vosk-model-small-ja-0.22",
    "ko-KR": "vosk-model-small-ko-0.22", "zh-CN": "vosk-model-small-cn-0.22",
}


def list_models() -> list[str]:
    if not MODELS_DIR.exists():
        return []
    return sorted(p.name for p in MODELS_DIR.iterdir() if p.is_dir())


def model_path(name: str) -> Path:
    return MODELS_DIR / name


def download_model(name: str, progress: Callable[[float, str], None]) -> Path:
    """Download + unzip ``name`` into models/. Raises on failure."""
    MODELS_DIR.mkdir(exist_ok=True)
    target = MODELS_DIR / name
    if target.exists():
        return target
    zip_path = MODELS_DIR / f"{name}.zip"
    try:
        req = urllib.request.Request(BASE_URL.format(name=name), headers={"User-Agent": "Handsfree"})
        with urllib.request.urlopen(req, timeout=30) as resp, open(zip_path, "wb") as fh:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if total:
                    progress(done / total * 0.9, f"Downloading... {done // 1_000_000} / {total // 1_000_000} MB")
        progress(0.92, "Unpacking...")
        with zipfile.ZipFile(zip_path) as zf:
            root = MODELS_DIR.resolve()
            for member in zf.namelist():                       # block zip-slip
                if not (MODELS_DIR / member).resolve().is_relative_to(root):
                    raise RuntimeError("Unsafe path in model archive")
            zf.extractall(MODELS_DIR)
        progress(1.0, "Model installed")
        return target
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise
    finally:
        zip_path.unlink(missing_ok=True)
