import { FaceLandmarker, FilesetResolver } from '@mediapipe/tasks-vision';
import type { GestureResult } from './HandTracker';

export type TrackingState =
  | 'IDLE'
  | 'INITIALISING'
  | 'SEARCHING'
  | 'TRACKING'
  | 'FACE_LOST'
  | 'ERROR';

export interface HeadPosition {
  x: number;
  y: number;
}

type GestureCb = (result: GestureResult) => void;
type StateCb    = (state: TrackingState, error?: string) => void;

const BLINK_THRESHOLD = 0.22;
const DOUBLE_BLINK_MAX_DELAY_MS = 500;

export class FaceTracker {
  private landmarker: FaceLandmarker | null = null;
  private animFrameId: number | null = null;
  private lastTimestamp = -1;
  private onGesture: GestureCb;
  private onState: StateCb;

  private overlayCanvas: HTMLCanvasElement | null = null;

  // Blink state
  private wasEyesClosed = false;
  private lastBlinkTime = 0;

  constructor(onGesture: GestureCb, onState: StateCb) {
    this.onGesture = onGesture;
    this.onState   = onState;
  }

  async init(): Promise<void> {
    this.onState('INITIALISING');
    try {
      const vision = await FilesetResolver.forVisionTasks(chrome.runtime.getURL('mediapipe/wasm'));
      this.landmarker = await FaceLandmarker.createFromOptions(vision, {
        baseOptions: {
          modelAssetPath: chrome.runtime.getURL('mediapipe/face_landmarker.task'),
          delegate: 'CPU',
        },
        runningMode: 'VIDEO',
        numFaces: 1,
        minFaceDetectionConfidence: 0.3,
        minFacePresenceConfidence: 0.3,
        minTrackingConfidence:     0.3,
      });
      this.onState('SEARCHING');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      this.onState('ERROR', `Model initialisation failed: ${msg}`);
    }
  }
  
  setOverlayCanvas(canvas: HTMLCanvasElement) {
    this.overlayCanvas = canvas;
  }

  start(videoEl: HTMLVideoElement): void {
    if (!this.landmarker) return;
    this.stop();

    const tick = () => {
      if (!this.landmarker) return;

      if (videoEl.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
        const nowMs = performance.now();
        if (nowMs !== this.lastTimestamp) {
          this.lastTimestamp = nowMs;
          const result = this.landmarker.detectForVideo(videoEl, nowMs);
          const faces  = result.faceLandmarks;

          if (faces && faces.length > 0 && faces[0].length > 1) {
            const lm = faces[0];
            const nose = lm[1];
            
            // EAR calculation for double blink
            // Left eye (viewer right): 362, 385, 387, 263, 373, 380
            // Right eye (viewer left): 33, 160, 158, 133, 153, 144
            const dist = (a: any, b: any) => Math.hypot(a.x - b.x, a.y - b.y);
            const calcEAR = (i: number[]) => {
              return (dist(lm[i[1]], lm[i[5]]) + dist(lm[i[2]], lm[i[4]])) / (2.0 * dist(lm[i[0]], lm[i[3]]));
            };
            
            const leftEAR = calcEAR([362, 385, 387, 263, 373, 380]);
            const rightEAR = calcEAR([33, 160, 158, 133, 153, 144]);
            const avgEAR = (leftEAR + rightEAR) / 2.0;
            
            let pinchFired = false;
            const isEyesClosed = avgEAR < BLINK_THRESHOLD;
            
            if (isEyesClosed && !this.wasEyesClosed) {
              // Blink started
              if (nowMs - this.lastBlinkTime < DOUBLE_BLINK_MAX_DELAY_MS) {
                pinchFired = true; // Double blink!
                this.lastBlinkTime = 0; // reset
              } else {
                this.lastBlinkTime = nowMs;
              }
            }
            this.wasEyesClosed = isEyesClosed;

            this.onGesture({
              mode: 'NAVIGATE',
              position: { x: 1 - nose.x, y: nose.y },
              scrollDelta: 0,
              pinchFired
            });
            this.onState('TRACKING');
            
            this.drawOverlay(videoEl, lm, pinchFired);
          } else {
            this.onState('FACE_LOST');
            this.clearOverlay();
          }
        }
      }
      this.animFrameId = requestAnimationFrame(tick);
    };
    this.animFrameId = requestAnimationFrame(tick);
  }

  private clearOverlay() {
    const ctx = this.overlayCanvas?.getContext('2d');
    ctx?.clearRect(0, 0, this.overlayCanvas!.width, this.overlayCanvas!.height);
  }

  private drawOverlay(_videoEl: HTMLVideoElement, lm: any[], clickFired: boolean) {
    if (!this.overlayCanvas) return;
    const canvas = this.overlayCanvas;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const w = canvas.width  = canvas.offsetWidth  || 320;
    const h = canvas.height = canvas.offsetHeight || 240;
    ctx.clearRect(0, 0, w, h);

    const color = clickFired ? '#ff6600' : '#00ff88';
    
    // Calculate bounding box for head
    let minX = 1, maxX = 0, minY = 1, maxY = 0;
    for (let i = 0; i < lm.length; i++) {
      if (lm[i].x < minX) minX = lm[i].x;
      if (lm[i].x > maxX) maxX = lm[i].x;
      if (lm[i].y < minY) minY = lm[i].y;
      if (lm[i].y > maxY) maxY = lm[i].y;
    }
    
    // Draw Head Box (mirrored X)
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.rect((1 - maxX) * w, minY * h, (maxX - minX) * w, (maxY - minY) * h);
    ctx.stroke();

    // Calculate Eye Centers
    const leftEyeIdx = [362, 385, 387, 263, 373, 380];
    const rightEyeIdx = [33, 160, 158, 133, 153, 144];
    
    const getCenter = (indices: number[]) => {
      let cx = 0, cy = 0;
      for(let i of indices) {
        cx += lm[i].x; cy += lm[i].y;
      }
      return { x: cx / indices.length, y: cy / indices.length };
    };
    
    const leftCenter = getCenter(leftEyeIdx);
    const rightCenter = getCenter(rightEyeIdx);

    // Draw Eye Circles
    ctx.fillStyle = '#00ff88'; // small green circle
    ctx.beginPath();
    ctx.arc((1 - leftCenter.x) * w, leftCenter.y * h, 4, 0, Math.PI * 2);
    ctx.fill();
    
    ctx.beginPath();
    ctx.arc((1 - rightCenter.x) * w, rightCenter.y * h, 4, 0, Math.PI * 2);
    ctx.fill();

    // Mode label
    ctx.fillStyle = color;
    ctx.font = 'bold 16px sans-serif';
    ctx.fillText('HEAD TRACKING', 10, 24);
  }

  stop(): void {
    if (this.animFrameId !== null) cancelAnimationFrame(this.animFrameId);
    this.animFrameId = null;
    this.clearOverlay();
  }

  dispose(): void {
    this.stop();
    if (this.landmarker) {
      this.landmarker.close();
      this.landmarker = null;
    }
    this.onState('IDLE');
  }
}

