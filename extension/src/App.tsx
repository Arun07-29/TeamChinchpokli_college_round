import { useState, useEffect, useRef, useCallback } from 'react';
import './index.css';
import type { MessageType } from './shared/types';
import { CameraPreview } from './components/CameraPreview';
import { useTracking } from './hooks/useTracking';
import { ChatInterface } from './components/ChatInterface';
import type { TrackingState } from './tracking/FaceTracker';
import { useSettings } from './hooks/useSettings';
import {
  startSession, recordCommand,
  endAndSaveSession, loadHistory, clearHistory,
  type SessionSummary,
} from './shared/analytics';

// ─── Cursor computation constants ────────────────────────────────────────────
const DEAD_ZONE      = 0.015;   // fraction of frame — suppress micro-jitter
const CURSOR_FPS_CAP = 60;      // 60 FPS ultra-smooth, low-latency cursor updates
const MS_PER_FRAME   = 1000 / CURSOR_FPS_CAP;

// ─── Helpers ─────────────────────────────────────────────────────────────────
function clamp(v: number, lo = 0, hi = 1) { return Math.max(lo, Math.min(hi, v)); }

function trackingLabel(state: TrackingState): string {
  switch (state) {
    case 'IDLE':         return 'Idle';
    case 'INITIALISING': return 'Initialising model…';
    case 'SEARCHING':    return 'Searching for subject…';
    case 'TRACKING':     return 'Tracking ✓';
    case 'FACE_LOST':    return 'Tracking lost — move into view';
    case 'ERROR':        return 'Error';
  }
}

function trackingColor(state: TrackingState): string {
  if (state === 'TRACKING')     return '#28a745';
  if (state === 'FACE_LOST')    return '#ffc107';
  if (state === 'ERROR')        return '#dc3545';
  return '#6c757d';
}

function formatDuration(ms: number | null): string {
  if (ms === null) return 'Ongoing';
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

function formatTime(ts: number): string {
  return new Date(ts).toLocaleString(undefined, {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

// ─── SessionHistoryPanel ─────────────────────────────────────────────────────
function SessionHistoryPanel({
  history,
  onClear,
}: {
  history: SessionSummary[];
  onClear: () => void;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (history.length === 0) {
    return (
      <div style={{ fontSize: '12px', color: '#888', padding: '8px 0' }}>
        No session data recorded yet.
      </div>
    );
  }

  return (
    <div>
      <div style={{
        maxHeight: '220px', overflowY: 'auto',
        borderRadius: '6px', border: '1px solid #e0e0e0',
      }}>
        {history.map((h) => {
          const isExp = expanded === h.id;
          const totalCmds = h.successCount + h.failureCount + h.cancelCount;
          return (
            <div key={h.id} style={{ borderBottom: '1px solid #f0f0f0' }}>
              {/* Summary row */}
              <button
                onClick={() => setExpanded(isExp ? null : h.id)}
                style={{
                  width: '100%', textAlign: 'left',
                  padding: '8px 12px', background: isExp ? '#f0f7ff' : '#fff',
                  border: 'none', cursor: 'pointer',
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  fontSize: '12px',
                }}
                aria-expanded={isExp}
              >
                <span>
                  <strong>{formatTime(h.startedAt)}</strong>
                  {' · '}{h.trackingMode}
                  {' · '}{formatDuration(h.durationMs)}
                </span>
                <span style={{ color: '#888' }}>
                  {totalCmds} cmd{totalCmds !== 1 ? 's' : ''} {isExp ? '▲' : '▼'}
                </span>
              </button>

              {/* Detail panel */}
              {isExp && (
                <div style={{ padding: '8px 14px 12px', background: '#f8f9fa', fontSize: '11px' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '6px', marginBottom: '8px' }}>
                    <div style={{ textAlign: 'center', padding: '4px', background: '#d4edda', borderRadius: '4px', color: '#155724' }}>
                      <div style={{ fontWeight: 700, fontSize: '14px' }}>{h.successCount}</div>
                      <div>Success</div>
                    </div>
                    <div style={{ textAlign: 'center', padding: '4px', background: '#f8d7da', borderRadius: '4px', color: '#721c24' }}>
                      <div style={{ fontWeight: 700, fontSize: '14px' }}>{h.failureCount}</div>
                      <div>Failed</div>
                    </div>
                    <div style={{ textAlign: 'center', padding: '4px', background: '#fff3cd', borderRadius: '4px', color: '#856404' }}>
                      <div style={{ fontWeight: 700, fontSize: '14px' }}>{h.cancelCount}</div>
                      <div>Cancelled</div>
                    </div>
                  </div>
                  {Object.keys(h.commandCounts).length > 0 && (
                    <div>
                      <strong style={{ display: 'block', marginBottom: '4px' }}>Commands used:</strong>
                      {Object.entries(h.commandCounts)
                        .sort(([, a], [, b]) => b - a)
                        .map(([cmd, count]) => (
                          <div key={cmd} style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0', borderBottom: '1px solid #eee' }}>
                            <span style={{ color: '#555' }}>{cmd}</span>
                            <span style={{ fontWeight: 600 }}>×{count}</span>
                          </div>
                        ))
                      }
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div style={{ marginTop: '10px', display: 'flex', gap: '8px', alignItems: 'center' }}>
        <button
          id="btn-clear-analytics"
          className="danger"
          onClick={onClear}
          style={{ fontSize: '12px', padding: '6px 14px' }}
        >
          Delete Local Session Data
        </button>
        <span style={{ fontSize: '11px', color: '#999' }}>
          Removes all {history.length} session summaries from device storage.
        </span>
      </div>
    </div>
  );
}

// ─── App ─────────────────────────────────────────────────────────────────────
function App() {
  // ── Settings ───────────────────────────────────────────────────
  const { settings, updateSettings, resetSettings, loaded: settingsLoaded } = useSettings();

  // ── Session ────────────────────────────────────────────────────
  const [isActive,      setIsActive]      = useState(false);
  const [sessionError,  setSessionError]  = useState<string | null>(null);
  const [activeTabId,   setActiveTabId]   = useState<number | null>(null);

  // ── Camera ─────────────────────────────────────────────────────
  const videoElRef    = useRef<HTMLVideoElement | null>(null);
  const [isCameraReady, setIsCameraReady] = useState(false);

  // ── Tracking ───────────────────────────────────────────────────
  const [isTracking,    setIsTracking]    = useState(false);
  const overlayCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const {
    trackingMode,
    setTrackingMode,
    trackingState,
    trackingError,
    gestureMode,
    latestPositionRef,
    latestGestureRef,
    initAndStart,
    stopTracking,
  } = useTracking();

  // Sync trackingMode from settings on load (settings are authoritative)
  useEffect(() => {
    if (settingsLoaded) setTrackingMode(settings.trackingMode);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settingsLoaded]);

  // ── Calibration ────────────────────────────────────────────────
  const neutralRef   = useRef<{ x: number; y: number } | null>(null);
  const [hasNeutral, setHasNeutral] = useState(false);

  // Restore persisted calibration on settings load
  useEffect(() => {
    if (settingsLoaded && settings.calibrationNeutral) {
      neutralRef.current = settings.calibrationNeutral;
      setHasNeutral(true);
    }
  }, [settingsLoaded]); // run once after load
  // eslint-disable-next-line react-hooks/exhaustive-deps

  // ── Analytics ──────────────────────────────────────────────────
  const [history, setHistory] = useState<SessionSummary[]>([]);
  useEffect(() => { loadHistory().then(setHistory); }, []);

  // ── Targeting & IntentShield ────────────────────────────────────
  const [isTargeting,  setIsTargeting]  = useState(false);
  const [isPaused,     setIsPaused]     = useState(false);
  const [targetingInfo, setTargetingInfo] = useState<string | null>(null);

  // ── Chat Interface ───────────────────────────────────────────────

  // We are removing the old useVoiceCommands from App.tsx since ChatInterface manages it.
  // We keep smoothRef and lastSendMsRef.

  // ── Cursor smoothing state (mutable, not React state) ──────────
  const smoothRef      = useRef({ x: 0.5, y: 0.5 }); // HEAD mode cursor
  const webSmoothRef   = useRef({ x: 0.5, y: 0.5 }); // RIGHT hand -> webpage cursor
  const webInFrameRef  = useRef(false);
  const panelSmoothRef = useRef({ x: 0.5, y: 0.5 }); // LEFT hand -> slide panel cursor
  const panelInFrameRef = useRef(false);
  const lastSendMsRef  = useRef(0);
  const localCursorRef = useRef<HTMLDivElement | null>(null);
  const activeTabIdRef = useRef<number | null>(null);
  activeTabIdRef.current = activeTabId;

  // ═══════════════════════════════════════════════════════════════
  // Session helpers
  // ═══════════════════════════════════════════════════════════════
  const handleStart = async () => {
    setSessionError(null);
    try {
      let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab) {
        const tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
        tab = tabs[0];
      }
      if (!tab || !tab.id) throw new Error('No active tab found.');

      // Activate session immediately across IntentLock
      setIsActive(true);
      setActiveTabId(tab.id as number);
      startSession(settings.trackingMode);

      // Write session flag to storage — content script watches this and auto-activates
      // This is the primary activation mechanism (race-free)
      await chrome.storage.local.set({ intentlock_session_active: true });

      // Belt-and-suspenders: also attempt direct injection + message (for already-open pages)
      try {
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          files: ['assets/content.js'],
        });
      } catch {
        // May already be injected via manifest — that's fine
      }

      // Retry ACTIVATE_SESSION up to 5 times with 200ms spacing
      let activated = false;
      for (let attempt = 0; attempt < 5 && !activated; attempt++) {
        await new Promise<void>((res) => {
          chrome.tabs.sendMessage(tab!.id!, { type: 'ACTIVATE_SESSION' } as MessageType, (resp) => {
            void chrome.runtime.lastError;
            if (resp?.success) activated = true;
            res();
          });
        });
        if (!activated) await new Promise(r => setTimeout(r, 200));
      }
    } catch (err: unknown) {
      setSessionError(err instanceof Error ? err.message : 'Failed to start session.');
    }
  };

  const handleStop = useCallback(() => {
    // Stop tracking before ending session so resources are released cleanly
    if (isTracking) {
      stopTracking();
      setIsTracking(false);
      neutralRef.current = null;
      setHasNeutral(false);
      smoothRef.current = { x: 0.5, y: 0.5 };
      webSmoothRef.current = { x: 0.5, y: 0.5 };
      panelSmoothRef.current = { x: 0.5, y: 0.5 };
      webInFrameRef.current = false;
      panelInFrameRef.current = false;
    }
    if (localCursorRef.current) localCursorRef.current.style.display = 'none';
    // Clear session flag from storage — content scripts will auto-deactivate via storage listener
    chrome.storage.local.set({ intentlock_session_active: false });
    if (activeTabId) {
      chrome.tabs.sendMessage(activeTabId, { type: 'DEACTIVATE_SESSION' } as MessageType);
      chrome.tabs.sendMessage(activeTabId, { type: 'CURSOR_HIDE' } as MessageType);
    }
    setIsActive(false);
    setActiveTabId(null);
    setIsPaused(false);
    setIsTargeting(false);
    recordCommand({ category: 'session', command: 'STOP_SESSION', success: true });
    endAndSaveSession(settings.maxSessionHistory).then(() => loadHistory().then(setHistory));
  }, [activeTabId, isTracking, stopTracking, settings.maxSessionHistory]);

  // ═══════════════════════════════════════════════════════════════
  // Global Tab Management
  // ═══════════════════════════════════════════════════════════════
  useEffect(() => {
    if (!isActive) return;

    const injectAndActivate = async (tabId: number, _url?: string) => {
      // Write session flag first — content script auto-activates via storage listener
      await chrome.storage.local.set({ intentlock_session_active: true });
      try {
        await chrome.scripting.executeScript({ target: { tabId }, files: ['assets/content.js'] });
      } catch (e) {} // May already be injected or internal page
      // Retry ACTIVATE_SESSION as belt-and-suspenders
      let activated = false;
      for (let attempt = 0; attempt < 5 && !activated; attempt++) {
        await new Promise<void>((res) => {
          chrome.tabs.sendMessage(tabId, { type: 'ACTIVATE_SESSION' } as MessageType, (resp) => {
            void chrome.runtime.lastError;
            if (resp?.success) activated = true;
            res();
          });
        });
        if (!activated) await new Promise(r => setTimeout(r, 200));
      }
      setActiveTabId(tabId);
    };

    const handleTabActivated = async (activeInfo: { tabId: number }) => {
      // Deactivate previous
      const prevTabId = activeTabIdRef.current;
      if (prevTabId) {
        chrome.tabs.sendMessage(prevTabId, { type: 'CURSOR_HIDE' } as MessageType, () => void chrome.runtime.lastError);
      }
      const tab = await chrome.tabs.get(activeInfo.tabId);
      await injectAndActivate(tab.id!, tab.url);
    };

    const handleTabUpdated = async (tabId: number, changeInfo: any, tab: chrome.tabs.Tab) => {
      if (changeInfo.status === 'complete' && tab.active) {
        await injectAndActivate(tabId, tab.url);
      }
    };

    chrome.tabs.onActivated.addListener(handleTabActivated);
    chrome.tabs.onUpdated.addListener(handleTabUpdated);

    return () => {
      chrome.tabs.onActivated.removeListener(handleTabActivated);
      chrome.tabs.onUpdated.removeListener(handleTabUpdated);
    };
  }, [isActive]);

  // ═══════════════════════════════════════════════════════════════
  // Tracking helpers
  // ═══════════════════════════════════════════════════════════════
  const handleStartTracking = useCallback(async () => {
    if (!videoElRef.current) {
      setSessionError('Camera must be running before starting tracking.');
      return;
    }
    setIsTracking(true);
    await initAndStart(videoElRef.current, overlayCanvasRef.current);
  }, [initAndStart]);

  const handleStopTracking = useCallback(() => {
    stopTracking();
    setIsTracking(false);
    // Clear calibration on explicit stop — update settings to drop persisted neutral
    neutralRef.current = null;
    setHasNeutral(false);
    smoothRef.current = { x: 0.5, y: 0.5 };
    updateSettings({ calibrationNeutral: null });
    if (activeTabId) {
      chrome.tabs.sendMessage(activeTabId, { type: 'CURSOR_HIDE' } as MessageType);
    }
  }, [stopTracking, activeTabId, updateSettings]);

  // ═══════════════════════════════════════════════════════════════
  // Calibration
  // ═══════════════════════════════════════════════════════════════
  const handleSetNeutral = useCallback(() => {
    const pos = latestPositionRef.current;
    if (!pos) return;
    neutralRef.current = { x: pos.x, y: pos.y };
    smoothRef.current  = { x: 0.5, y: 0.5 };
    setHasNeutral(true);
    // Persist calibration so user doesn't need to re-calibrate after reopening
    updateSettings({ calibrationNeutral: { x: pos.x, y: pos.y } });
  }, [latestPositionRef, updateSettings]);

  // ═══════════════════════════════════════════════════════════════
  // 1. Cursor Movement rAF loop (Smooth & Rate Limited)
  // ═══════════════════════════════════════════════════════════════
  useEffect(() => {
    if (!isTracking || !isActive || !activeTabId) return;
    if (trackingState !== 'TRACKING') return;

    let rafId: number;
    chrome.tabs.sendMessage(activeTabId, { type: 'CURSOR_SHOW' } as MessageType, () => void chrome.runtime.lastError);
    if (localCursorRef.current) localCursorRef.current.style.display = 'none';

    const tick = () => {
      const gesture = latestGestureRef?.current;
      const neutral = neutralRef.current;

      if (gesture) {
        if (trackingMode === 'HEAD') {
          // ── HEAD MODE: single cursor driven by face position ──────
          if (gesture.position) {
            let targetX = 0.5;
            let targetY = 0.5;
            if (neutral) {
              let dx = gesture.position.x - neutral.x;
              let dy = gesture.position.y - neutral.y;
              if (Math.abs(dx) < DEAD_ZONE) dx = 0;
              if (Math.abs(dy) < DEAD_ZONE) dy = 0;
              targetX = clamp(0.5 + dx * settings.sensitivity);
              targetY = clamp(0.5 + dy * settings.sensitivity);
            } else {
              // Auto-calibrate on first detected frame so cursor appears and tracks immediately!
              neutralRef.current = { x: gesture.position.x, y: gesture.position.y };
              setHasNeutral(true);
              updateSettings({ calibrationNeutral: { x: gesture.position.x, y: gesture.position.y } });
            }
            smoothRef.current = {
              x: settings.smoothAlpha * targetX + (1 - settings.smoothAlpha) * smoothRef.current.x,
              y: settings.smoothAlpha * targetY + (1 - settings.smoothAlpha) * smoothRef.current.y,
            };
            const now = performance.now();
            if (now - lastSendMsRef.current >= MS_PER_FRAME) {
              lastSendMsRef.current = now;
              chrome.tabs.sendMessage(activeTabId, {
                type: 'CURSOR_MOVE',
                x: smoothRef.current.x,
                y: smoothRef.current.y,
                gesture: gesture.mode
              } as MessageType, () => void chrome.runtime.lastError);
            }
          }
        } else {
          // ── HAND MODE: RIGHT hand -> WEBPAGE ONLY, LEFT hand -> SLIDE PANEL ONLY ──
          const now = performance.now();
          const timeOk = now - lastSendMsRef.current >= MS_PER_FRAME;
          const handSmoothAlpha = Math.max(settings.smoothAlpha, 0.35);

          // 1. RIGHT HAND drives the WEBPAGE cursor ONLY (Never touches slide panel)
          const rightHand = gesture.rightHand;
          if (rightHand?.position) {
            const targetX = rightHand.position.x;
            const targetY = rightHand.position.y;
            webSmoothRef.current = {
              x: handSmoothAlpha * targetX + (1 - handSmoothAlpha) * webSmoothRef.current.x,
              y: handSmoothAlpha * targetY + (1 - handSmoothAlpha) * webSmoothRef.current.y,
            };
            webInFrameRef.current = true;

            if (timeOk) {
              lastSendMsRef.current = now;
              chrome.tabs.sendMessage(activeTabId, {
                type: 'CURSOR_MOVE',
                x: webSmoothRef.current.x,
                y: webSmoothRef.current.y,
                gesture: rightHand.mode
              } as MessageType, () => void chrome.runtime.lastError);
            }
          } else if (webInFrameRef.current) {
            webInFrameRef.current = false;
            chrome.tabs.sendMessage(activeTabId, { type: 'CURSOR_HIDE' } as MessageType, () => void chrome.runtime.lastError);
          }

          // 2. LEFT HAND drives the SLIDE PANEL cursor ONLY (Never touches webpage)
          const leftHand = gesture.leftHand;
          if (leftHand?.position) {
            const targetX = leftHand.position.x;
            const targetY = leftHand.position.y;
            panelSmoothRef.current = {
              x: handSmoothAlpha * targetX + (1 - handSmoothAlpha) * panelSmoothRef.current.x,
              y: handSmoothAlpha * targetY + (1 - handSmoothAlpha) * panelSmoothRef.current.y,
            };
            panelInFrameRef.current = true;

            if (localCursorRef.current) {
              localCursorRef.current.style.display = 'flex';
              localCursorRef.current.style.left = `${panelSmoothRef.current.x * window.innerWidth}px`;
              localCursorRef.current.style.top  = `${panelSmoothRef.current.y * window.innerHeight}px`;
              if (leftHand.mode === 'PINCH') {
                localCursorRef.current.style.borderColor = '#ff6600';
                localCursorRef.current.style.backgroundColor = 'rgba(255,102,0,0.25)';
              } else if (leftHand.mode === 'SCROLL') {
                localCursorRef.current.style.borderColor = '#00ccff';
                localCursorRef.current.style.backgroundColor = 'rgba(0,204,255,0.25)';
              } else {
                localCursorRef.current.style.borderColor = '#a855f7'; // Purple outline for slide panel
                localCursorRef.current.style.backgroundColor = 'rgba(168,85,247,0.20)';
              }
            }
          } else {
            panelInFrameRef.current = false;
            if (localCursorRef.current) {
              localCursorRef.current.style.display = 'none';
            }
          }
        }
      }
      rafId = requestAnimationFrame(tick);
    };

    rafId = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(rafId);
      chrome.tabs.sendMessage(activeTabId, { type: 'CURSOR_HIDE' } as MessageType, () => void chrome.runtime.lastError);
      if (localCursorRef.current) localCursorRef.current.style.display = 'none';
    };
  }, [isTracking, isActive, activeTabId, trackingMode, hasNeutral, settings.sensitivity, settings.smoothAlpha, trackingState, updateSettings]);

  // ═══════════════════════════════════════════════════════════════
  // 2. Gesture Event rAF loop (Immediate, NO rate limit)
  // ═══════════════════════════════════════════════════════════════
  useEffect(() => {
    if (!isTracking || !isActive || !activeTabId) return;
    if (trackingState !== 'TRACKING') return;

    let rafId: number;
    let lastPinchWeb   = false; // webpage hand
    let lastPinchPanel = false; // panel hand (dual hand)

    const tick = () => {
      const gesture = latestGestureRef?.current;

      if (gesture) {
        if (trackingMode === 'HEAD') {
          // ── HEAD MODE: fire single gesture to webpage ─────────────
          if (gesture.pinchFired && !lastPinchWeb) {
            chrome.tabs.sendMessage(activeTabId, { type: 'PINCH_CLICK' } as MessageType, () => void chrome.runtime.lastError);
            lastPinchWeb = true;
          } else if (!gesture.pinchFired) {
            lastPinchWeb = false;
          }
          if (gesture.mode === 'SCROLL' && Math.abs(gesture.scrollDelta) > 0) {
            chrome.tabs.sendMessage(activeTabId, { type: 'SCROLL_DELTA', delta: gesture.scrollDelta } as MessageType, () => void chrome.runtime.lastError);
          }
        } else {
          // ── HAND MODE ──
          // 1. RIGHT HAND -> Webpage click & scroll
          const rightHand = gesture.rightHand;
          if (rightHand) {
            if (rightHand.pinchFired && !lastPinchWeb) {
              chrome.tabs.sendMessage(activeTabId, { type: 'PINCH_CLICK' } as MessageType, () => void chrome.runtime.lastError);
              lastPinchWeb = true;
            } else if (!rightHand.pinchFired) {
              lastPinchWeb = false;
            }
            if (rightHand.mode === 'SCROLL' && Math.abs(rightHand.scrollDelta) > 0) {
              chrome.tabs.sendMessage(activeTabId, { type: 'SCROLL_DELTA', delta: rightHand.scrollDelta } as MessageType, () => void chrome.runtime.lastError);
            }
          } else {
            lastPinchWeb = false;
          }

          // 2. LEFT HAND -> Slide panel click & scroll
          const leftHand = gesture.leftHand;
          if (leftHand) {
            if (leftHand.pinchFired && !lastPinchPanel) {
              // Click whatever side-panel element the left cursor is over
              if (localCursorRef.current) localCursorRef.current.style.pointerEvents = 'none';
              const px = panelSmoothRef.current.x * window.innerWidth;
              const py = panelSmoothRef.current.y * window.innerHeight;
              const el = document.elementFromPoint(px, py);
              if (el instanceof HTMLElement) el.click();
              if (localCursorRef.current) localCursorRef.current.style.pointerEvents = 'none';
              lastPinchPanel = true;
            } else if (!leftHand.pinchFired) {
              lastPinchPanel = false;
            }
            if (leftHand.mode === 'SCROLL' && Math.abs(leftHand.scrollDelta) > 0) {
              window.scrollBy({ top: leftHand.scrollDelta * 1000, behavior: 'auto' });
            }
          } else {
            lastPinchPanel = false;
          }
        }
      }
      rafId = requestAnimationFrame(tick);
    };

    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [isTracking, isActive, activeTabId, trackingMode, trackingState]);

  // Auto-start tracking when camera is ready
  useEffect(() => {
    if (isActive && isCameraReady && !isTracking) {
      handleStartTracking();
    }
    // Also handle auto-stop if not active
    if (!isActive && isTracking) {
      handleStopTracking();
    }
  }, [isActive, isCameraReady, isTracking]);

  // ═══════════════════════════════════════════════════════════════
  // Render
  // ═══════════════════════════════════════════════════════════════
  if (!settingsLoaded) {
    return <div style={{ padding: '20px', color: '#666' }}>Loading preferences…</div>;
  }

  return (
    <div className="container">

      {/* ── Header ─────────────────────────────────────────────── */}
      <div className="header">
        <div className="logo">IL</div>
        <div>
          <h1 className="title">IntentLock</h1>
          <span className={`status-badge ${isActive ? 'active' : ''}`}>
            {isActive ? (isPaused ? '⏸ Paused' : 'Active on Page') : 'Inactive'}
          </span>
        </div>
      </div>

      {/* ── Session error ────────────────────────────────────────── */}
      {sessionError && (
        <div
          id="session-error-msg"
          style={{ color: '#721c24', fontSize: '13px', padding: '8px', backgroundColor: '#f8d7da', borderRadius: '4px', border: '1px solid #f5c6cb', marginBottom: '4px' }}
        >
          {sessionError}
        </div>
      )}

      {/* ── Session controls ─────────────────────────────────────── */}
      <div className="section">
        <h2 className="section-title">Session Controls</h2>
        <div className="controls" style={{ marginBottom: '8px' }}>
          <button id="btn-start-session" className="primary" onClick={handleStart} disabled={isActive}>
            Start
          </button>
          <button
            id="btn-pause-resume-session"
            style={{
              background: isPaused ? '#28a745' : '#ffc107',
              color: isPaused ? '#fff' : '#333',
              border: 'none', padding: '8px 16px', borderRadius: '6px',
              fontWeight: 600, cursor: isActive ? 'pointer' : 'default',
              opacity: isActive ? 1 : 0.5,
            }}
            onClick={() => {
              if (!activeTabId) return;
              if (isPaused) {
                chrome.tabs.sendMessage(activeTabId, { type: 'SHIELD_RESUME' });
                setIsPaused(false);
              } else {
                chrome.tabs.sendMessage(activeTabId, { type: 'SHIELD_PAUSE' });
                setIsPaused(true);
              }
            }}
            disabled={!isActive}
          >
            {isPaused ? '▶ Resume' : '⏸ Pause'}
          </button>
          <button id="btn-stop-session" className="danger" onClick={handleStop} disabled={!isActive}>
            Stop
          </button>
        </div>
        
        {/* ── Tab Navigation ─────────────────────────────────────── */}
        {isActive && (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '8px' }}>
              <button
                className="secondary"
                onClick={() => chrome.tabs.create({ url: 'https://www.google.com' })}
                style={{ padding: '8px', fontSize: '12px' }}
              >
                ➕ New Tab
              </button>
              <button
                className="secondary"
                onClick={() => activeTabId && chrome.tabs.remove(activeTabId)}
                style={{ padding: '8px', fontSize: '12px' }}
              >
                ✖ Close Tab
              </button>
              <button
                className="secondary"
                onClick={async () => {
                  const tabs = await chrome.tabs.query({ currentWindow: true });
                  const activeIndex = tabs.findIndex(t => t.active);
                  const prevTab = tabs[(activeIndex - 1 + tabs.length) % tabs.length];
                  if (prevTab && prevTab.id) chrome.tabs.update(prevTab.id, { active: true });
                }}
                style={{ padding: '8px', fontSize: '12px' }}
              >
                ⬅ Prev Tab
              </button>
              <button
                className="secondary"
                onClick={async () => {
                  const tabs = await chrome.tabs.query({ currentWindow: true });
                  const activeIndex = tabs.findIndex(t => t.active);
                  const nextTab = tabs[(activeIndex + 1) % tabs.length];
                  if (nextTab && nextTab.id) chrome.tabs.update(nextTab.id, { active: true });
                }}
                style={{ padding: '8px', fontSize: '12px' }}
              >
                Next Tab ➡
              </button>
            </div>
            <p style={{ fontSize: '11px', color: '#888', margin: '8px 0 0' }}>
              Keyboard: <kbd>Alt+Shift+P</kbd> = Pause/Resume · <kbd>Alt+Shift+S</kbd> = Stop
            </p>
          </>
        )}
      </div>



      {/* ── Camera + Tracking ────────────────────────────────────── */}
      <div className="section">
        <h2 className="section-title">Webcam Tracking</h2>

        {isActive ? (
          <CameraPreview
            videoElRef={videoElRef}
            onCameraReady={setIsCameraReady}
            keepAlive={isActive}
            onCanvasReady={(canvas) => { overlayCanvasRef.current = canvas; }}
          />
        ) : (
          <div style={{ padding: '20px', textAlign: 'center', color: '#666', border: '1px dashed #ccc', borderRadius: '4px' }}>
            Click <strong>Start</strong> above to activate the camera.
          </div>
        )}

        {/* Mode Selector */}
        <div style={{ marginTop: '12px', display: 'flex', gap: '8px', alignItems: 'center' }}>
          <label htmlFor="tracking-mode-select" className="info-label">Mode:</label>
          <select
            id="tracking-mode-select"
            value={trackingMode}
            onChange={(e) => {
              const newMode = e.target.value as 'HEAD' | 'HAND';
              setTrackingMode(newMode);
              updateSettings({ trackingMode: newMode });
              if (isTracking && videoElRef.current) {
                stopTracking();
                neutralRef.current = null;
                setHasNeutral(false);
                updateSettings({ calibrationNeutral: null });
                initAndStart(videoElRef.current, overlayCanvasRef.current, newMode);
              }
            }}
            disabled={!isActive}
            style={{ padding: '4px', borderRadius: '4px', border: '1px solid #ccc' }}
          >
            <option value="HEAD">Head Movement</option>
            <option value="HAND">Hand Movement</option>
          </select>
        </div>

        {/* Removed manual tracking controls as tracking now auto-starts with the camera */}

        {isTracking && (
          <div style={{ marginTop: '10px' }}>
            <div className="info-row">
              <span className="info-label">Tracking Status</span>
              <span style={{ fontWeight: 500, color: trackingColor(trackingState) }}>
                {trackingLabel(trackingState)}
              </span>
            </div>
            {/* Gesture mode — only shown in HAND mode */}
            {trackingMode === 'HAND' && trackingState === 'TRACKING' && (
              <div style={{ marginTop: '8px', padding: '6px 10px', background: '#f8fafc', borderRadius: '6px', border: '1px solid #e2e8f0', fontSize: '11px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: '#16a34a', fontWeight: 600 }}>👉 Right Hand (Webpage):</span>
                  <span style={{ fontWeight: 500, color: '#334155' }}>
                    {gestureMode === 'PINCH' ? '🤏 Click Ready' : gestureMode === 'SCROLL' ? '✌ Scrolling' : '☝ Navigating'}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: '#9333ea', fontWeight: 600 }}>👈 Left Hand (Slide Panel):</span>
                  <span style={{ fontWeight: 500, color: '#334155' }}>Active</span>
                </div>
              </div>
            )}
            {trackingError && (
              <div style={{ color: '#dc3545', fontSize: '12px', marginTop: '4px' }}>
                {trackingError}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Conversational Assistant - below camera */}
      <ChatInterface 
        isActive={isActive} 
        geminiApiKey={import.meta.env.VITE_GEMINI_API_KEY ?? ''} 
        activeTabId={activeTabId}
        autoListen={isActive}
      />

      {/* ── Settings / Calibration ──────────────────────────────────────────── */}
      {isTracking && trackingState === 'TRACKING' && (
        <div className="section">
          <h2 className="section-title">Cursor Settings</h2>
          
          {trackingMode === 'HEAD' && (
            <>
              <p style={{ fontSize: '12px', color: '#666', margin: '0 0 10px' }}>
                Look straight ahead at the screen, keep comfortable, then set your neutral position.
              </p>
              {settings.calibrationNeutral && !hasNeutral && (
                <p style={{ fontSize: '11px', color: '#007bff', margin: '0 0 8px' }}>
                  ↺ Saved calibration loaded from last session.
                </p>
              )}

              <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
                <button id="btn-set-neutral" className="primary" onClick={handleSetNeutral} disabled={!isActive}>
                  {hasNeutral ? '↺ Reset Neutral Position' : 'Set Neutral Position'}
                </button>
              </div>

              {hasNeutral && (
                <>
                  <div className="info-row" style={{ alignItems: 'center' }}>
                    <label htmlFor="sensitivity-slider" className="info-label">
                      Sensitivity: <strong>{settings.sensitivity}×</strong>
                    </label>
                  </div>
                  <input
                    id="sensitivity-slider"
                    type="range"
                    min={1} max={10} step={0.5}
                    value={settings.sensitivity}
                    onChange={(e) => updateSettings({ sensitivity: parseFloat(e.target.value) })}
                    disabled={!isActive}
                    style={{ width: '100%', marginTop: '6px' }}
                    aria-label="Cursor sensitivity"
                  />
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#999', marginBottom: '12px' }}>
                    <span>Less</span><span>More</span>
                  </div>
                </>
              )}
            </>
          )}

          {(trackingMode === 'HAND' || hasNeutral) && (
            <>
              <div className="info-row" style={{ alignItems: 'center', marginTop: trackingMode === 'HAND' ? '0' : '12px' }}>
                <label htmlFor="smooth-slider" className="info-label">
                  Smoothing: <strong>{Math.round((1 - settings.smoothAlpha) * 100)}%</strong>
                </label>
              </div>
              <input
                id="smooth-slider"
                type="range"
                min={0.05} max={0.5} step={0.01}
                value={settings.smoothAlpha}
                onChange={(e) => updateSettings({ smoothAlpha: parseFloat(e.target.value) })}
                disabled={!isActive}
                style={{ width: '100%', marginTop: '6px' }}
                aria-label="Cursor smoothing"
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#999' }}>
                <span>Smoother (slower)</span><span>Snappier (less smooth)</span>
              </div>

              {!isActive && (
                <p style={{ fontSize: '12px', color: '#007bff', marginTop: '10px' }}>
                  ↑ Click <strong>Start</strong> in Session Controls to activate cursor on the page.
                </p>
              )}
              {isActive && (
                <p style={{ fontSize: '12px', color: '#28a745', marginTop: '10px' }}>
                  ✓ Virtual cursor is active.{' '}
                  {trackingMode === 'HEAD' ? 'Move your head to control it.' : 'Move your hand to control it.'}
                </p>
              )}
            </>
          )}
        </div>
      )}


      {/* ── Element Targeting ────────────────────────────────────── */}
      <div className="section">
        <h2 className="section-title">Element Targeting</h2>
        <p style={{ fontSize: '12px', color: '#666', margin: '0 0 10px' }}>
          Show numbered badges on visible interactive elements. Select by number or name.
        </p>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <button
            id="btn-show-targets"
            className="primary"
            disabled={!isActive || isTargeting}
            onClick={() => {
              if (!activeTabId) return;
              chrome.tabs.sendMessage(activeTabId, { type: 'TARGETING_ENABLE' }, () => setIsTargeting(true));
            }}
          >
            Show Targets
          </button>
          <button
            id="btn-hide-targets"
            disabled={!isTargeting}
            onClick={() => {
              if (!activeTabId) return;
              chrome.tabs.sendMessage(activeTabId, { type: 'TARGETING_DISABLE' });
              setIsTargeting(false);
              setTargetingInfo(null);
            }}
          >
            Hide Targets
          </button>
        </div>
        {isTargeting && (
          <div style={{ marginTop: '10px', fontSize: '12px', color: '#28a745' }}>
            ● Targeting active — say "select 3" or "select Submit"
          </div>
        )}
        {targetingInfo && (
          <div style={{ marginTop: '6px', padding: '6px 8px', background: '#f0f8ff', borderRadius: '4px', fontSize: '12px', whiteSpace: 'pre-line' }}>
            {targetingInfo}
          </div>
        )}
      </div>

      {/* ── IntentShield ─────────────────────────────────────────── */}
      <div className="section">
        <h2 className="section-title">IntentShield Safety</h2>
        <p style={{ fontSize: '12px', color: '#666', margin: '0 0 10px' }}>
          Cursor movement never triggers clicks automatically. Choose how clicks activate.
        </p>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
          <input
            id="dwell-toggle"
            type="checkbox"
            checked={settings.dwellEnabled}
            disabled={!isActive}
            onChange={(e) => updateSettings({ dwellEnabled: e.target.checked })}
          />
          <label htmlFor="dwell-toggle" style={{ fontSize: '13px' }}>
            Enable dwell-to-click ({(settings.dwellMs / 1000).toFixed(1)}s hold)
          </label>
        </div>
        {settings.dwellEnabled && (
          <div style={{ marginBottom: '8px' }}>
            <label htmlFor="dwell-duration-slider" style={{ fontSize: '12px', color: '#555' }}>
              Dwell duration: <strong>{(settings.dwellMs / 1000).toFixed(1)}s</strong>
            </label>
            <input
              id="dwell-duration-slider"
              type="range"
              min={500} max={3000} step={100}
              value={settings.dwellMs}
              disabled={!isActive}
              onChange={(e) => updateSettings({ dwellMs: parseInt(e.target.value) })}
              style={{ width: '100%', marginTop: '4px' }}
              aria-label="Dwell duration"
            />
            <p style={{ fontSize: '11px', color: '#888', margin: '4px 0 0' }}>
              Say <strong>"dwell click"</strong> or hold the cursor still to fire a click.
              Say <strong>"cancel"</strong> to abort.
            </p>
          </div>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '10px' }}>
          <input
            id="shield-confirm-toggle"
            type="checkbox"
            checked={settings.shieldConfirmEnabled}
            disabled={!isActive}
            onChange={(e) => updateSettings({ shieldConfirmEnabled: e.target.checked })}
          />
          <label htmlFor="shield-confirm-toggle" style={{ fontSize: '13px' }}>
            Confirm high-impact actions (delete, buy, submit…)
          </label>
        </div>
        <div style={{ padding: '8px', background: '#fff8e1', borderRadius: '4px', fontSize: '11px', color: '#7d6608' }}>
          <strong>Limitations:</strong> High-impact detection uses keyword heuristics (delete, buy, submit…).
          Custom UIs with non-standard labels may not be caught. Always review actions carefully.
        </div>
      </div>

      {/* ── Local Analytics & Settings ───────────────────────────── */}
      <div className="section">
        <h2 className="section-title">Local Analytics &amp; Settings</h2>

        {/* Session history */}
        <div style={{ marginBottom: '20px' }}>
          <h3 style={{ fontSize: '13px', margin: '0 0 10px', fontWeight: 600 }}>
            Session History ({history.length} / {settings.maxSessionHistory} sessions)
          </h3>
          <SessionHistoryPanel
            history={history}
            onClear={async () => {
              await clearHistory();
              setHistory([]);
            }}
          />
        </div>

        {/* Settings management */}
        <div style={{ borderTop: '1px solid #eee', paddingTop: '14px' }}>
          <h3 style={{ fontSize: '13px', margin: '0 0 10px', fontWeight: 600 }}>Preferences</h3>

          <div style={{ marginBottom: '12px' }}>
            <label htmlFor="max-history-input" style={{ fontSize: '12px', color: '#555', display: 'block', marginBottom: '4px' }}>
              Max session history retained: <strong>{settings.maxSessionHistory}</strong>
            </label>
            <input
              id="max-history-input"
              type="range"
              min={5} max={200} step={5}
              value={settings.maxSessionHistory}
              onChange={(e) => updateSettings({ maxSessionHistory: parseInt(e.target.value) })}
              style={{ width: '100%' }}
              aria-label="Max sessions retained"
            />
          </div>



          <button
            id="btn-reset-settings"
            className="danger"
            onClick={() => {
              resetSettings();
              // Sync tracking mode UI back to default
              setTrackingMode('HEAD');
              neutralRef.current = null;
              setHasNeutral(false);
            }}
            style={{ fontSize: '12px', padding: '6px 14px' }}
          >
            Reset All Settings to Defaults
          </button>
          <p style={{ fontSize: '11px', color: '#999', margin: '6px 0 0' }}>
            Resets mode, sensitivity, smoothing, dwell, and safety preferences.
            Does not delete session history.
          </p>
        </div>

        <p style={{ fontSize: '10px', color: '#bbb', margin: '14px 0 0', lineHeight: 1.5 }}>
          Privacy: IntentLock stores only aggregate command counts and timestamps locally.
          No camera frames, biometric data, voice recordings, or browsing URLs are stored.
        </p>
      </div>

      {/* ── Local Side Panel Cursor (Left Hand Only) ──────────────── */}
      <div
        ref={localCursorRef}
        style={{
          display: 'none',
          position: 'fixed', width: '28px', height: '28px',
          borderRadius: '50%', backgroundColor: 'rgba(168,85,247,0.20)',
          border: '2.5px solid #a855f7',
          boxShadow: '0 2px 12px rgba(168,85,247,0.35)',
          zIndex: 2147483646, pointerEvents: 'none',
          alignItems: 'center', justifyContent: 'center',
          transform: 'translate(-50%,-50%)',
          willChange: 'left, top',
          transition: 'border-color 0.15s, background-color 0.15s'
        }}
      >
        <div style={{ width: '7px', height: '7px', borderRadius: '50%', backgroundColor: '#a855f7', flexShrink: 0 }} />
      </div>

    </div>
  );
}

export default App;
