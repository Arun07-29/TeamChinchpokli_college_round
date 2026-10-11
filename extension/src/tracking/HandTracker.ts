import { HandLandmarker, FilesetResolver } from '@mediapipe/tasks-vision';
import type { TrackingState, HeadPosition as Position } from './FaceTracker';
import { OneEuroFilter2D } from './OneEuroFilter';

// ── Gesture types ────────────────────────────────────────────────────────────
export type GestureMode = 'NAVIGATE' | 'SCROLL' | 'PINCH' | 'NONE';

export interface HandGestureState {
  mode: GestureMode;
  position: Position | null;
  scrollDelta: number;
  pinchFired: boolean;
}

export interface GestureResult {
  mode: GestureMode;
  /** Index fingertip position, normalised [0,1], mirror-corrected */
  position: Position | null;
  /** Signed scroll delta (positive = scroll down). Only meaningful in SCROLL mode. */
  scrollDelta: number;
  /** True for exactly ONE frame when a new pinch triggers — use to fire one click */
  pinchFired: boolean;

  // Hand tracking specifics for dual-hand control
  leftHand?: HandGestureState;
  rightHand?: HandGestureState;
}

type GestureCb = (result: GestureResult) => void;
type StateCb   = (state: TrackingState, error?: string) => void;

// ── Tuning constants ─────────────────────────────────────────────────────────
const PINCH_CLOSE_THRESHOLD = 0.07;  // normalised distance to enter pinch
const PINCH_OPEN_THRESHOLD  = 0.10;  // must separate past this to reset
const SCROLL_DEADZONE       = 0.012; // suppress micro-jitter in scroll

/**
 * HandTracker v2
 *
 * Gesture priority (highest → lowest):
 *   1. PINCH   — thumb tip + index tip distance < threshold  → one click per pinch
 *   2. SCROLL  — index + middle both extended, ring not      → vertical scroll
 *   3. NAVIGATE — index extended only                        → cursor movement
 *   4. NONE    — no hand / ambiguous
 *
 * Draws a landmark overlay on an optional canvas element.
 */
export class HandTracker {
  private landmarker: HandLandmarker | null = null;
  private animFrameId: number | null = null;
  private lastTimestamp = -1;
  private onGesture: GestureCb;
  private onState: StateCb;

  // Independent state & 1€ filter for each hand
  private leftState = {
    filter: new OneEuroFilter2D(1.0, 0.025, 1.0),
    isPinched: false,
    lastScrollY: null as number | null,
    lastSeen: 0,
  };
  private rightState = {
    filter: new OneEuroFilter2D(1.0, 0.025, 1.0),
    isPinched: false,
    lastScrollY: null as number | null,
    lastSeen: 0,
  };

  // Persistent role lock for single-hand gestures. MediaPipe handedness is the
  // source of truth; the lock only prevents a brief classification dropout
  // from changing the active target.
  private singleHandRole: 'RIGHT' | 'LEFT' | null = null;
  private singleHandLastSeen = 0;

  // Optional canvas overlay for visual feedback
  private overlayCanvas: HTMLCanvasElement | null = null;

  constructor(onGesture: GestureCb, onState: StateCb) {
    this.onGesture = onGesture;
    this.onState   = onState;
  }

  async init(): Promise<void> {
    this.onState('INITIALISING');
    try {
      const vision = await FilesetResolver.forVisionTasks(
        chrome.runtime.getURL('mediapipe/wasm')
      );
      this.landmarker = await HandLandmarker.createFromOptions(vision, {
        baseOptions: {
          modelAssetPath: chrome.runtime.getURL('mediapipe/hand_landmarker.task'),
          delegate: 'CPU',
        },
        runningMode: 'VIDEO',
        numHands: 2,
        minHandDetectionConfidence: 0.3,
        minHandPresenceConfidence: 0.3,
        minTrackingConfidence:     0.3,
      });
      this.onState('SEARCHING');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      this.onState('ERROR', `Hand model init failed: ${msg}`);
    }
  }

  /** Pass a canvas element to receive landmark drawing each frame */
  setOverlayCanvas(canvas: HTMLCanvasElement | null) {
    this.overlayCanvas = canvas;
  }

  start(videoEl: HTMLVideoElement): void {
    if (!this.landmarker) {
      this.onState('ERROR', 'Tracker not initialised — call init() first.');
      return;
    }
    this.stop();

    const tick = () => {
      if (!this.landmarker) return;
      if (videoEl.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
        const nowMs = performance.now();
        if (nowMs !== this.lastTimestamp) {
          this.lastTimestamp = nowMs;
          this.processFrame(videoEl, nowMs);
        }
      }
      this.animFrameId = requestAnimationFrame(tick);
    };

    this.animFrameId = requestAnimationFrame(tick);
  }

  private processFrame(videoEl: HTMLVideoElement, nowMs: number): void {
    const result = this.landmarker!.detectForVideo(videoEl, nowMs);
    const hands = result.landmarks;

    if (!hands || hands.length === 0) {
      this.onState('FACE_LOST');
      this.leftState.lastScrollY = null;
      this.rightState.lastScrollY = null;
      if (nowMs - this.singleHandLastSeen > 500) {
        this.singleHandRole = null;
      }
      this.clearCanvas();
      this.onGesture({ mode: 'NONE', position: null, scrollDelta: 0, pinchFired: false });
      return;
    }

    this.onState('TRACKING');
    // Resize & clear overlay canvas once per frame before per-hand draws
    if (this.overlayCanvas) {
      this.overlayCanvas.width  = this.overlayCanvas.offsetWidth  || 320;
      this.overlayCanvas.height = this.overlayCanvas.offsetHeight || 240;
      const ctx = this.overlayCanvas.getContext('2d');
      ctx?.clearRect(0, 0, this.overlayCanvas.width, this.overlayCanvas.height);
    }
    this.clearCanvas();

    let leftHandState: HandGestureState | undefined;
    let rightHandState: HandGestureState | undefined;

    // Determine hand roles (user's perspective: Right = Webpage, Left = Slide Panel).
    // Never infer roles from screen position when handedness is available: a
    // right hand must remain the webpage hand even when it crosses the frame.
    const handRoles: ('RIGHT' | 'LEFT')[] = [];

    for (let i = 0; i < hands.length; i++) {
      const handedness = result.handednesses[i]?.[0]?.categoryName?.toLowerCase();
      if (handedness === 'right' || handedness === 'left') {
        handRoles[i] = handedness === 'right' ? 'RIGHT' : 'LEFT';
        continue;
      }

      // Defensive fallback for a malformed/partial MediaPipe result. This is
      // only used when handedness is unavailable, never for normal tracking.
      const rawX = 1 - (hands[i][8]?.x ?? hands[i][0]?.x ?? 0.5);
      handRoles[i] = rawX >= 0.5 ? 'RIGHT' : 'LEFT';
    }

    if (hands.length === 1) {
      this.singleHandRole = handRoles[0] ?? this.singleHandRole;
      this.singleHandLastSeen = nowMs;
    } else {
      this.singleHandRole = null;
    }

    for (let i = 0; i < hands.length; i++) {
      const lm = hands[i];
      if (lm.length < 21) continue;

      const isUserRight = handRoles[i] === 'RIGHT';
      const stateObj = isUserRight ? this.rightState : this.leftState;
      stateObj.lastSeen = nowMs;

      // In mirrored view (matching user perspective in webcam preview):
      const rawX = 1 - lm[8].x;
      const rawY = lm[8].y;

      // ── Key landmarks ──
      const thumbTip   = lm[4];
      const indexTip   = lm[8];
      const indexMCP   = lm[5];
      const middleTip  = lm[12];
      const middleMCP  = lm[9];
      const ringTip    = lm[16];
      const ringPIP    = lm[14];

      // ── Finger extension (tip clearly above MCP) ──
      const indexExtended  = indexTip.y  < indexMCP.y  - 0.04;
      const middleExtended = middleTip.y < middleMCP.y - 0.04;
      const ringExtended   = ringTip.y   < ringPIP.y   - 0.02;

      // ── 1€ Filtered index tip position (Ultra-smooth stationary, zero-lag dynamic) ──
      const filtered = stateObj.filter.filter(rawX, rawY, nowMs);
      const pos: Position = { x: filtered.x, y: filtered.y };

      // ── Pinch distance ──
      const dx = thumbTip.x - indexTip.x;
      const dy = thumbTip.y - indexTip.y;
      const pinchDist = Math.sqrt(dx * dx + dy * dy);

      // Draw overlay for this hand with its specific role label
      this.drawOverlaySingleHand(videoEl, lm, pinchDist, indexExtended, middleExtended, isUserRight);

      let mode: GestureMode = 'NONE';
      let scrollDelta = 0;
      let pinchFired = false;

      // ── Gesture Priority 1: PINCH ──
      if (pinchDist < PINCH_CLOSE_THRESHOLD) {
        pinchFired = !stateObj.isPinched;
        stateObj.isPinched = true;
        stateObj.lastScrollY = null;
        mode = 'PINCH';
      } 
      // Reset pinch when fingers open
      else if (pinchDist > PINCH_OPEN_THRESHOLD) {
        stateObj.isPinched = false;
        
        // ── Gesture Priority 2: SCROLL (index + middle, ring down) ──
        if (indexExtended && middleExtended && !ringExtended) {
          const avgY = (indexTip.y + middleTip.y) / 2;
          if (stateObj.lastScrollY !== null) {
            const raw = avgY - stateObj.lastScrollY;
            scrollDelta = Math.abs(raw) > SCROLL_DEADZONE ? raw : 0;
          }
          stateObj.lastScrollY = avgY;
          mode = 'SCROLL';
        } 
        // ── Gesture Priority 3: NAVIGATE (index only) ──
        else {
          stateObj.lastScrollY = null;
          if (indexExtended) {
            mode = 'NAVIGATE';
          }
        }
      } else {
        // Between thresholds, maintain mode but don't fire events
        if (indexExtended && middleExtended && !ringExtended) {
          mode = 'SCROLL';
          stateObj.lastScrollY = (indexTip.y + middleTip.y) / 2;
        } else if (indexExtended) {
          mode = 'NAVIGATE';
        }
      }

      const handResult: HandGestureState = { mode, position: pos, scrollDelta, pinchFired };
      if (isUserRight) {
        rightHandState = handResult;
      } else {
        leftHandState = handResult;
      }
    }

    // Default primary output to right hand (webpage), fallback to left hand
    const mainResult = rightHandState || leftHandState || { mode: 'NONE', position: null, scrollDelta: 0, pinchFired: false };

    this.onGesture({
      ...mainResult,
      rightHand: rightHandState,
      leftHand: leftHandState,
    });
  }

  // ── Overlay drawing ──────────────────────────────────────────────────────

  private clearCanvas() {
    if (!this.overlayCanvas) return;
    const ctx = this.overlayCanvas.getContext('2d');
    ctx?.clearRect(0, 0, this.overlayCanvas.width, this.overlayCanvas.height);
  }

  private drawOverlaySingleHand(
    _videoEl: HTMLVideoElement,
    lm: Array<{ x: number; y: number; z: number }>,
    pinchDist: number,
    indexExtended: boolean,
    middleExtended: boolean,
    isUserRight: boolean,
  ) {
    if (!this.overlayCanvas) return;
    const canvas = this.overlayCanvas;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Canvas size is already set/cleared in processFrame per-frame
    const w = canvas.width  || 320;
    const h = canvas.height || 240;

    // Connection pairs to draw skeleton
    const connections: [number, number][] = [
      [0,1],[1,2],[2,3],[3,4],     // thumb
      [0,5],[5,6],[6,7],[7,8],     // index
      [0,9],[9,10],[10,11],[11,12],// middle
      [0,13],[13,14],[14,15],[15,16],// ring
      [0,17],[17,18],[18,19],[19,20],// pinky
      [5,9],[9,13],[13,17],        // palm
    ];

    const isPinching = pinchDist < PINCH_CLOSE_THRESHOLD;
    const baseColor = isUserRight ? '#00ff88' : '#c084fc'; // Green for Web (Right), Purple for Panel (Left)
    const colour = isPinching ? '#ff6600' : indexExtended && middleExtended ? '#00ccff' : baseColor;

    // Draw connections
    ctx.strokeStyle = colour;
    ctx.lineWidth = 2;
    ctx.globalAlpha = 0.85;
    for (const [a, b] of connections) {
      ctx.beginPath();
      // Landmarks are in [0,1] normalised — mirror X to match mirrored video
      ctx.moveTo((1 - lm[a].x) * w, lm[a].y * h);
      ctx.lineTo((1 - lm[b].x) * w, lm[b].y * h);
      ctx.stroke();
    }

    // Draw joint dots
    for (let i = 0; i < lm.length; i++) {
      const isTip = [4, 8, 12].includes(i);
      ctx.beginPath();
      ctx.arc((1 - lm[i].x) * w, lm[i].y * h, isTip ? 5 : 3, 0, Math.PI * 2);
      ctx.fillStyle = isTip ? colour : 'rgba(255,255,255,0.7)';
      ctx.fill();
    }

    // Gesture label with dedicated target name
    ctx.globalAlpha = 1;
    ctx.fillStyle = colour;
    ctx.font = 'bold 12px sans-serif';
    const actionLabel = isPinching ? '🤏 PINCH' : indexExtended && middleExtended ? '✌ SCROLL' : indexExtended ? '☝ NAV' : '';
    if (isUserRight) {
      ctx.fillText(`👉 RIGHT (Web): ${actionLabel}`, Math.max(8, w - 170), h - 10);
    } else {
      ctx.fillText(`👈 LEFT (Panel): ${actionLabel}`, 8, h - 10);
    }
  }

  stop(): void {
    if (this.animFrameId !== null) {
      cancelAnimationFrame(this.animFrameId);
      this.animFrameId = null;
    }
    this.leftState.filter.reset();
    this.rightState.filter.reset();
    this.singleHandRole = null;
  }

  dispose(): void {
    this.stop();
    this.clearCanvas();
    if (this.landmarker) {
      this.landmarker.close();
      this.landmarker = null;
    }
    this.onState('IDLE');
  }
}
