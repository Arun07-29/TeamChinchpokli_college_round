import type { MessageType } from '../shared/types';
import { executeVoiceCommand } from './voice-actions';
import {
  enableTargeting, disableTargeting,
  selectByNumber, selectByName,
} from './targeting';
import {
  pause, resume, isPausedState,
  startDwell, cancelDwell, cleanup as shieldCleanup,
} from './intentshield';

// ── Guard against double-injection ───────────────────────────────────────────
if (!(window as any).__INTENTLOCK_INJECTED) {
  (window as any).__INTENTLOCK_INJECTED = true;


  // ── Session indicator ───────────────────────────────────────────
  let indicator: HTMLDivElement | null = null;
  function createIndicator() {
    if (indicator) return;
    indicator = document.createElement('div');
    indicator.id = 'intentlock-indicator';
    Object.assign(indicator.style, {
      position: 'fixed', bottom: '20px', right: '20px',
      padding: '6px 12px', backgroundColor: '#007bff',
      color: '#fff', borderRadius: '20px',
      boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
      fontFamily: 'sans-serif', fontSize: '12px', fontWeight: 'bold',
      zIndex: '2147483647', pointerEvents: 'none',
    });
    indicator.textContent = 'IntentLock Active';
    const container = document.body || document.documentElement;
    if (container) container.appendChild(indicator);
  }
  function removeIndicator() { indicator?.remove(); indicator = null; }

  // ── Virtual cursor ───────────────────────────────────────────────
  let cursor: HTMLDivElement | null = null;

  function createCursor() {
    if (cursor) return;
    cursor = document.createElement('div');
    cursor.id = 'intentlock-cursor';
    Object.assign(cursor.style, {
      position: 'fixed', width: '28px', height: '28px',
      borderRadius: '50%', backgroundColor: 'rgba(0,123,255,0.18)',
      border: '2.5px solid rgba(0,123,255,0.85)',
      boxShadow: '0 2px 12px rgba(0,123,255,0.35)',
      zIndex: '2147483646', pointerEvents: 'none',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      transform: 'translate(-50%,-50%)', left: '50%', top: '50%',
      willChange: 'left, top',
      transition: 'border-color 0.15s',
    });
    const dot = document.createElement('div');
    Object.assign(dot.style, {
      width: '7px', height: '7px', borderRadius: '50%',
      backgroundColor: '#007bff', flexShrink: '0',
    });
    cursor.appendChild(dot);
    const container = document.body || document.documentElement;
    if (container) container.appendChild(cursor);
  }

  let cursorX = window.innerWidth  / 2;
  let cursorY = window.innerHeight / 2;

  function moveCursor(x: number, y: number, gesture?: string) {
    if (!cursor) createCursor();
    if (!cursor) return;
    if (cursor.style.display === 'none') {
      cursor.style.display = 'flex';
    }
    cursorX = Math.max(0, Math.min(1, x)) * window.innerWidth;
    cursorY = Math.max(0, Math.min(1, y)) * window.innerHeight;
    
    // Tint the cursor based on gesture
    if (isPausedState()) {
      cursor.style.borderColor = 'rgba(255,193,7,0.85)';
      cursor.style.backgroundColor = 'rgba(255,193,7,0.18)';
    } else if (gesture === 'PINCH') {
      cursor.style.borderColor = '#ff6600';
      cursor.style.backgroundColor = 'rgba(255,102,0,0.2)';
    } else if (gesture === 'SCROLL') {
      cursor.style.borderColor = '#00ccff';
      cursor.style.backgroundColor = 'rgba(0,204,255,0.2)';
    } else {
      cursor.style.borderColor = 'rgba(0,123,255,0.85)';
      cursor.style.backgroundColor = 'rgba(0,123,255,0.18)';
    }

    cursor.style.left = `${cursorX}px`;
    cursor.style.top  = `${cursorY}px`;
  }

  function showCursor()  { if (cursor) cursor.style.display = 'flex'; }
  function hideCursor()  { if (cursor) cursor.style.display = 'none'; }
  function removeCursor(){ cursor?.remove(); cursor = null; }

  // ── Keyboard shortcut — Alt+Shift+P to pause/resume, Alt+Shift+S to stop ──
  let isActive = false; // will be flipped by storage auto-activate below if session is running

  // ── Auto-activate if session already running (fixes injection race) ─────────
  // Deferred so all helper functions (createIndicator, createCursor, etc.) are defined first.
  chrome.storage.local.get('intentlock_session_active', (result) => {
    if (result.intentlock_session_active === true && !isActive) {
      isActive = true;
      createIndicator();
      createCursor();
      resume();
    }
  });

  // Listen for storage changes (start/stop from side panel)
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== 'local' || !('intentlock_session_active' in changes)) return;
    const nowActive = changes.intentlock_session_active.newValue === true;
    if (nowActive && !isActive) {
      isActive = true;
      createIndicator();
      createCursor();
      resume();
    } else if (!nowActive && isActive) {
      fullStop();
    }
  });

  document.addEventListener('keydown', (e: KeyboardEvent) => {
    if (!isActive) return;
    if (e.altKey && e.shiftKey && e.key === 'P') {
      e.preventDefault();
      if (isPausedState()) resume(); else pause();
      updateIndicator();
    }
    if (e.altKey && e.shiftKey && e.key === 'S') {
      e.preventDefault();
      fullStop();
    }
  });

  function updateIndicator() {
    if (indicator) {
      indicator.textContent = isPausedState() ? 'IntentLock ⏸ Paused' : 'IntentLock Active';
      indicator.style.backgroundColor = isPausedState() ? '#ffc107' : '#007bff';
      indicator.style.color = isPausedState() ? '#333' : '#fff';
    }
    if (cursor) {
      cursor.style.borderColor = isPausedState()
        ? 'rgba(255,193,7,0.85)' : 'rgba(0,123,255,0.85)';
    }
  }

  function fullStop() {
    isActive = false;
    pause();
    shieldCleanup();
    disableTargeting();
    removeIndicator();
    removeCursor();
  }

  // ── Message router ───────────────────────────────────────────────
  chrome.runtime.onMessage.addListener((message: MessageType, _sender, sendResponse) => {
    switch (message.type) {

      // ── Session ────────────────────────────────────────────────
      case 'ACTIVATE_SESSION':
        isActive = true;
        createIndicator();
        createCursor();
        resume();
        sendResponse({ success: true });
        break;

      case 'DEACTIVATE_SESSION':
        fullStop();
        sendResponse({ success: true });
        break;

      case 'SESSION_STATUS_QUERY':
        sendResponse({ isActive });
        break;

      // ── Cursor ─────────────────────────────────────────────────
      case 'CURSOR_MOVE':
        if (!isActive) {
          isActive = true;
          createIndicator();
        }
        moveCursor(message.x, message.y, message.gesture);
        break;

      case 'PINCH_CLICK':
        if (!isPausedState()) {
          if (!cursor) createCursor();
          if (cursor) {
            // Hide cursor briefly so elementFromPoint finds what's under it
            cursor.style.display = 'none';
            const el = document.elementFromPoint(cursorX, cursorY) as HTMLElement | null;
            cursor.style.display = 'flex';

            if (el && el.id !== 'intentlock-cursor' && el.id !== 'intentlock-targeting-host') {
              el.click();
              // Visual flash feedback
              cursor.style.backgroundColor = 'rgba(255,100,0,0.5)';
              cursor.style.borderColor = '#ff6600';
              setTimeout(() => {
                if (cursor) {
                  cursor.style.backgroundColor = 'rgba(0,123,255,0.18)';
                  cursor.style.borderColor = isPausedState() ? 'rgba(255,193,7,0.85)' : 'rgba(0,123,255,0.85)';
                }
              }, 200);
            }
          }
        }
        sendResponse({ success: true });
        break;

      case 'SCROLL_DELTA':
        if (!isPausedState()) {
          // delta is normalised [0,1] range — scale to pixels
          window.scrollBy({ top: message.delta * 600, behavior: 'auto' });
        }
        sendResponse({ success: true });
        break;

      case 'CURSOR_SHOW':
        isActive = true;
        createCursor();
        showCursor();
        sendResponse({ success: true });
        break;

      case 'CURSOR_HIDE':
        hideCursor();
        sendResponse({ success: true });
        break;

      // ── Voice ──────────────────────────────────────────────────
      case 'VOICE_COMMAND': {
        if (!isActive) { sendResponse({ success: false }); break; }

        // Shield intercepts pause/cancel at voice level
        if (message.command === 'PAUSE_CONTROLS') {
          pause(); updateIndicator(); sendResponse({ success: true }); break;
        }
        if (message.command === 'RESUME_CONTROLS') {
          resume(); updateIndicator(); sendResponse({ success: true }); break;
        }
        if (message.command === 'CANCEL_DWELL') {
          cancelDwell(); sendResponse({ success: true }); break;
        }

        if (isPausedState()) { sendResponse({ success: false }); break; }

        const success = executeVoiceCommand(message.command, message.arg);
        sendResponse({ success });
        break;
      }

      // ── Targeting ──────────────────────────────────────────────
      case 'TARGETING_ENABLE':
        if (isActive) { enableTargeting(); sendResponse({ success: true }); }
        else sendResponse({ success: false });
        break;

      case 'TARGETING_DISABLE':
        disableTargeting();
        sendResponse({ success: true });
        break;

      case 'TARGETING_SELECT_NUMBER': {
        const result = selectByNumber(message.n);
        sendResponse(result);
        break;
      }

      case 'TARGETING_SELECT_NAME': {
        const result = selectByName(message.name);
        sendResponse(result);
        break;
      }

      // ── IntentShield ───────────────────────────────────────────
      case 'SHIELD_PAUSE':
        pause(); updateIndicator(); sendResponse({ success: true });
        break;

      case 'SHIELD_RESUME':
        resume(); updateIndicator(); sendResponse({ success: true });
        break;

      case 'DWELL_CLICK':
        if (isActive && !isPausedState()) {
          startDwell(message.x, message.y);
          sendResponse({ success: true });
        } else {
          sendResponse({ success: false });
        }
        break;
    }
  });

  console.log('IntentLock content script ready (v2).');
}
