# IntentLock — V1

> **Hands-free browser control** via head or hand tracking and voice commands.  
> No account required. No data sent to any server. All session data stays on your device.

---

## Table of Contents

1. [What it does](#what-it-does)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Using the Extension](#using-the-extension)
5. [Voice Commands Reference](#voice-commands-reference)
6. [Permissions](#permissions)
7. [Privacy](#privacy)
8. [Known Limitations](#known-limitations)
9. [Testing](#testing)
10. [Development Build](#development-build)

---

## What it does

IntentLock adds a virtual mouse cursor to any web page that you control by moving your head (or hand) in front of your webcam. Voice commands trigger scrolling, clicking, form input, and navigation. A safety layer called **IntentShield** prevents accidental clicks by requiring either a dwell hold or an explicit voice command — cursor movement alone never triggers a click.

**Core features:**
- **Head tracking** — nose-tip landmark drives a smoothed virtual cursor
- **Hand tracking** — wrist position as an alternative movement mode
- **Calibration** — set a neutral position; calibration is saved and survives panel restarts
- **Dwell-to-click** — hold still for a configurable duration to fire a click
- **Voice commands** — scroll, click, focus, type, navigate, show/hide targets
- **Numbered element targeting** — overlays numbered badges on all interactive elements
- **IntentShield** — high-impact actions (delete, buy, submit…) require confirmation
- **Local analytics** — session summaries stored on device only
- **Keyboard shortcuts** — `Alt+Shift+P` pause/resume, `Alt+Shift+S` stop

---

## Installation

### Prerequisites
- Google Chrome (or Chromium-based browser) version 116 or later
- A working webcam
- Node.js 18+ and npm (for building from source)

### Install the pre-built extension

1. **Build first** (see [Development Build](#development-build)) or use an already-built `dist/` directory.
2. Open Chrome and navigate to `chrome://extensions/`
3. Enable **Developer mode** (toggle in the top-right corner)
4. Click **Load unpacked**
5. Select the `dist/` folder inside this `extension/` directory
6. IntentLock appears in the Chrome toolbar

### Open the side panel

Click the IntentLock icon in the toolbar. The side panel opens on the right side of the browser window.

---

## Configuration

All settings persist across extension restarts via `chrome.storage.local`.

| Setting | Default | Range | Description |
|---|---|---|---|
| Tracking Mode | HEAD | HEAD / HAND | Input device for cursor movement |
| Sensitivity | 4× | 1–10 | How far the cursor moves per unit of head movement |
| Smoothing | 0.18 (alpha) | 0.05–0.5 | EMA smoothing — lower = smoother but laggier |
| Calibration Neutral | null | auto | Saved neutral head position (two numbers, not biometric) |
| Dwell Enabled | Off | On/Off | Enable hold-to-click |
| Dwell Duration | 1.2 s | 0.5–3 s | Hold time before click fires |
| Shield Confirm | On | On/Off | Require confirmation for high-impact actions |
| Max Session History | 50 | 5–200 | Sessions retained in local storage |

### Resetting

- **Reset All Settings** — restores all preferences to defaults, clears saved calibration
- **Delete Local Session Data** — removes all saved session summaries

---

## Using the Extension

### Typical workflow

1. **Start Camera** — click "Start Camera" in the Webcam Tracking section. Grant camera permission if prompted.
2. **Start Tracking** — click "Start Tracking". The model initialises (first run may take a few seconds).
3. **Calibrate** — look straight ahead (or hold hand comfortably) and click "Set Neutral Position". The virtual cursor appears centred on the page.
4. **Start Session** — click "Start" in Session Controls. The IntentLock Active badge appears at the bottom-right of the page.
5. **Adjust sensitivity** — use the Sensitivity slider if the cursor moves too much or too little.
6. **Start Listening** — click "Start Listening" in Voice Commands. Say a command (e.g. "scroll down").
7. **Stop** — click "Stop" or say "stop session". All resources are released.

### Pause and resume

- **UI button**: ⏸ Pause / ▶ Resume in Session Controls
- **Keyboard**: `Alt+Shift+P`
- **Voice**: "pause controls" / "resume controls"

When paused, the cursor turns yellow and dwell clicks are disabled. Tracking stops but the camera stream continues.

---

## Voice Commands Reference

| Say this | Action |
|---|---|
| `scroll down` | Scroll page down by 50% of viewport height |
| `scroll up` | Scroll page up |
| `scroll to top` | Jump to top of page |
| `scroll to bottom` | Jump to bottom of page |
| `go back` | Browser history back |
| `go forward` | Browser history forward |
| `show targets` | Overlay numbered badges on all interactive elements |
| `hide targets` | Remove badges |
| `select 3` | Activate element #3 from the targeting overlay |
| `select Submit` | Activate element whose label contains "Submit" |
| `click Primary Action` | Click element whose text contains "Primary Action" |
| `focus search` | Focus input whose placeholder/name/id contains "search" |
| `type hello world` | Type text into the currently focused input |
| `dwell click` | Trigger a dwell click at the current cursor position |
| `cancel` | Cancel an in-progress dwell |
| `pause controls` | Pause all interaction |
| `resume controls` | Resume after pause |
| `stop session` | End the session and release all resources |

---

## Permissions

| Permission | Reason |
|---|---|
| `sidePanel` | Open the IntentLock UI in the browser side panel |
| `activeTab` | Inject the virtual cursor and message content scripts on the active tab |
| `scripting` | Execute the content script on demand (only when a session is started) |
| `storage` | Persist user preferences and session summaries locally via `chrome.storage.local` |
| `tabs` | Query the active tab URL to block restricted pages; receive tab-removed events for camera permission flow |
| `<all_urls>` (host permission) | Required by `scripting` to inject the content script on user-navigated pages |

No network requests are made by IntentLock itself. Browser speech recognition may contact Google's speech servers depending on your browser configuration.

---

## Privacy

IntentLock is designed with privacy as a hard constraint:

**What is stored locally (`chrome.storage.local`):**
- Your chosen tracking mode, sensitivity, and other UI preferences
- Saved calibration: two normalised floating-point numbers (x, y) representing neutral head position. No image, no face mesh, no identity data.
- Session summaries: start time, duration, command category counts, success/failure totals

**What is NEVER stored:**
- Raw camera frames or video
- Face or hand landmark coordinates (used only in memory for cursor position)
- Biometric templates or identity profiles
- Voice audio or full dictated text transcripts
- Browsing URLs or page content

**Browser speech recognition note:**  
Chrome's `webkitSpeechRecognition` API may send audio to Google's servers for processing. IntentLock does not control this. Audio is not saved by IntentLock regardless.

---

## Known Limitations

| Area | Limitation |
|---|---|
| **Restricted pages** | Cannot run on `chrome://`, `edge://`, or `about:` pages (Chrome policy) |
| **Iframes** | Cross-origin iframes (e.g. embedded YouTube, payment widgets) are isolated from the content script and cannot be targeted |
| **Complex web apps** | Single-page apps with custom focus management (e.g. some Google Docs modals) may not respond to synthesised `.click()` events |
| **IntentShield heuristics** | High-impact detection is keyword-based. Custom UIs using non-standard button labels ("Proceed", "Yes, continue") will not be caught |
| **Hand tracking accuracy** | MediaPipe hand detection is less stable than face detection in poor light or with rapid movement |
| **Voice recognition** | Requires an internet connection (browser sends audio to Google). Not available offline. Does not support all languages — currently fixed to `en-US` |
| **Model load time** | First `Start Tracking` may take 3–8 seconds to download and initialise the MediaPipe WASM model |
| **Multiple monitors** | The virtual cursor coordinate system is relative to the current viewport. Multi-monitor setups may behave unexpectedly if the window spans screens |
| **Side panel quirk** | Chrome's side panel does not receive standard `getUserMedia` camera access on some builds. If the camera fails, reload the extension |

---

## Testing

### Using the built-in test page

After building, open the test page in Chrome:

1. In Chrome, navigate to: `chrome-extension://<YOUR_EXTENSION_ID>/test.html`
   - Find your extension ID on `chrome://extensions/`
2. Open the IntentLock side panel
3. Follow the complete interaction flow below

### Validated interaction checklist

- [ ] Camera starts and shows live video preview
- [ ] Head tracking initialises (status changes: IDLE → INITIALISING → SEARCHING → TRACKING)
- [ ] Set Neutral Position locks the cursor to centre
- [ ] Session Start activates the "IntentLock Active" badge on the test page
- [ ] Moving head moves the virtual cursor across the page
- [ ] **Sensitivity slider** changes cursor speed in real time
- [ ] **Smoothing slider** changes cursor lag in real time
- [ ] Dwell: enable dwell, hold cursor still → progress ring appears → click fires
- [ ] Say "cancel" while dwell ring is showing → ring disappears, no click
- [ ] Voice "scroll down" scrolls the page
- [ ] Voice "show targets" → numbered badges appear on all links, buttons, inputs
- [ ] Voice "select 2" activates element #2
- [ ] Voice "select Submit" activates the Submit Form button (or shows ambiguity list)
- [ ] Voice "focus search" → search field receives focus
- [ ] Voice "type hello world" → text appears in focused input
- [ ] Dwell-clicking "Delete Account" → confirmation overlay appears
- [ ] Confirming the overlay → button activates (flashes)
- [ ] Cancelling the overlay → nothing happens
- [ ] Alt+Shift+P → indicator turns yellow, cursor turns yellow
- [ ] Alt+Shift+P again → resumes, cursor turns blue
- [ ] Stop button → session ends, indicator disappears, cursor disappears, tracking stops
- [ ] Reopen panel → settings are preserved, calibration neutral is restored
- [ ] Session History panel shows the completed session with correct counts
- [ ] "Delete Local Session Data" → history cleared
- [ ] "Reset All Settings" → preferences return to defaults

---

## Development Build

```bash
# Install dependencies
cd extension
npm install

# Production build (TypeScript check + Vite bundle → dist/)
npm run build

# Development server (side panel only — no extension context)
npm run dev
```

### Build output

| File | Description |
|---|---|
| `dist/assets/background.js` | Service worker — opens side panel on click |
| `dist/assets/content.js` | Content script — cursor, dwell, targeting, IntentShield |
| `dist/assets/sidepanel.js` | React side panel — all tracking and settings UI |
| `dist/assets/sidepanel.css` | Side panel styles |
| `dist/manifest.json` | Extension manifest v3 |
| `dist/mediapipe/` | MediaPipe WASM + model files (copied by prebuild script) |
