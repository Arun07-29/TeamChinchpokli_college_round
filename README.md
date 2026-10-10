# Handsfree — Stage 6: Settings & Accessibility Dashboard

One modern window that controls everything: hand tracking, voice commands, dictation and browser control.
Free to use. Speech defaults to Google's free web recogniser (needs internet); an offline Vosk engine is one setting away. Stage 2's gesture logic is kept, now configurable.

> Experimental prototype, not a certified assistive device. Gestures and speech can misfire — don't use it for
> payments or other sensitive actions. Pinch-clicking and voice control are **OFF** until you turn them on.

## Setup (Windows, PyCharm)
1. Extract the ZIP and open the `Handsfree` folder in PyCharm. Use a **Python 3.11 (64-bit)** interpreter.
2. In the terminal:
```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```
If `PyAudio` fails to install, voice features will show a clear message in the dashboard; hand control still works.

## First run — 5 steps
1. Press **▶ Start**. The camera card shows your hand; the status list turns green.
2. Move your index fingertip to move the pointer.
3. **Scroll:** raise your **index + middle finger together** (other fingers folded) and move your hand up/down — the pointer stays still. Or press **S** for **Scroll Mode** (whole palm scrolls); press **S** again to return.
4. Flip **Pinch to click** on (or press **C**) and test on a harmless page.
5. Want voice? Flip **Voice control** (needs internet — default engine is Google's free recogniser), press Start, then say
   *"hey handsfree scroll down"*. For private/offline use: Settings → Dictation → Engine = Offline, then *Download model*.

## Dashboard
| Part | What it does |
|---|---|
| Start / Pause / Resume / **Emergency Stop** / Exit | Lifecycle. Emergency Stop releases camera + mic and switches pinch-click off. |
| State + Mode badges | Running/Paused/Stopped and Cursor / Scroll / Voice / Dictation Mode |
| Camera | Live preview with hand landmarks, tracking area, scroll anchor |
| Quick switches | Pinch to click · Hand tracking · Voice control · Browser control · Talk now |
| System status | Webcam, hand tracking, cursor, scrolling, voice, microphone, dictation, browser — Running / Paused / Off / Error, with the reason |
| Activity | Everything Handsfree did or couldn't do, plus the last phrase it heard |

Shortcuts: `S` Scroll/Cursor · `C` pinch-click (when the window is focused) · global: `F8` Scroll/Cursor, `F9` Talk, `F12` Emergency stop
(configurable). Moving the mouse into the top-left corner also triggers an emergency stop (PyAutoGUI failsafe).

## Settings (all saved to `config.json`, applied immediately)
* **General** – theme, preview, auto-start, global shortcuts
* **Hand & Cursor** – camera choice, speed, smoothing, tiny-shake filter, calibration wizard, pinch distance, click cooldown,
  right-click and double-click gestures (thumb + middle / ring / little finger)
* **Scrolling** – two-finger scroll on/off, speed, dead zone, reverse direction
* **Voice** – microphone, wake phrase / push-to-talk / always listening, listening window, mic sensitivity, apps you allow by voice
* **Dictation** – start/stop, stop phrase, spoken punctuation, capitalisation, engine (offline Vosk or Google online), language, model
* **Browser** – on/off, live connection status, search engine, home page, "ask before risky actions"

Invalid or missing values are replaced by safe defaults (a warning appears in Activity). A corrupt `config.json`
is kept as `config.corrupt-<time>.json` and fresh defaults are written.

## Voice cheat-sheet
`click · double click · right click · scroll up/down [3] · page down · scroll mode · cursor mode · voice mode · start dictation ·
pause · resume · press enter · type hello · go back · refresh · new tab · close tab · go to youtube dot com · search for cats ·
open notepad · switch window · emergency stop`. In Dictation Mode say "comma", "period", "new line", "scratch that", "stop dictation".
Risky actions (close tab/window, open a site by voice) ask you to say **yes** or **no** first.

## Project structure
```
main.py  config_manager.py  config.json  requirements.txt
core/      app_controller.py  mode_manager.py  status.py  actions.py  confirmation.py  hotkeys.py
gestures/  gesture_engine.py  cursor_controller.py  scroll_controller.py  calibration.py  camera.py
voice/     speech_engine.py  session.py  commands.py  command_router.py  dictation.py  microphones.py  model_manager.py
browser/   browser_controller.py
ui/        dashboard.py  settings_window.py  status_panel.py  theme.py
legacy/    handsfree_stage2.py   (your original Stage 2 script, untouched)
tests/     test_logic.py         (python -m unittest discover -s tests)
```
Note: the Stage 2 ZIP had only the gesture script, so the voice and browser modules were written new for this stage.

## Troubleshooting
* **"Hey handsfree" not responding** – check: (1) Voice control switch is ON and you pressed Start; (2) the Microphone row says *Listening*; (3) the Activity box shows `Heard "..."` — if it shows something different from what you said, speak closer/slower or use *Talk now* (push-to-talk) instead; (4) Google engine needs internet.
* **Camera won't open** – close other apps using it; Windows Settings → Privacy → Camera. Try another camera in Settings.
* **"Wrong MediaPipe version"** – `pip install mediapipe==0.10.21` (needs Python 3.11).
* **Voice: "model not found"** – Settings → Dictation → *Download model*, or switch the engine to Google (sends audio online).
* **Voice: microphone unavailable** – Windows privacy settings for the microphone; reinstall `PyAudio`.
* **Browser actions** use the default browser and send keyboard shortcuts to the window in front, so focus it first.
* Log file: `handsfree.log` in the project folder.
