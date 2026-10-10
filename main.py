"""Handsfree - Stage 6: Settings & Accessibility Dashboard.

Run:  python main.py
"""
import logging
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))


def main() -> int:
    logging.basicConfig(filename=APP_DIR / "handsfree.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    try:
        import customtkinter as ctk
    except ImportError:
        print("The dashboard needs 'customtkinter'.\nRun:  python -m pip install -r requirements.txt")
        return 1

    from config_manager import ConfigManager
    from core.app_controller import AppController
    from ui.dashboard import Dashboard

    ctk.set_default_color_theme("blue")
    controller = AppController(ConfigManager())
    app = Dashboard(controller)
    try:
        app.mainloop()
    finally:
        controller.shutdown()          # always release the camera and microphone
    return 0


if __name__ == "__main__":
    sys.exit(main())
