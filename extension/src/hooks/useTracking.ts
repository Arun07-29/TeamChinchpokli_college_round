import { useRef, useState, useCallback } from 'react';
import { FaceTracker } from '../tracking/FaceTracker';
import { HandTracker } from '../tracking/HandTracker';
import type { TrackingState, HeadPosition } from '../tracking/FaceTracker';
import type { GestureMode, GestureResult } from '../tracking/HandTracker';

export type TrackingMode = 'HEAD' | 'HAND';

export interface TrackingHook {
  trackingMode: TrackingMode;
  setTrackingMode: (mode: TrackingMode) => void;
  trackingState: TrackingState;
  trackingError: string | null;
  gestureMode: GestureMode;
  /** Mutable ref — read in rAF without triggering re-renders */
  latestPositionRef: React.MutableRefObject<HeadPosition | null>;
  /** Mutable ref — read in rAF for gesture actions */
  latestGestureRef: React.MutableRefObject<GestureResult | null>;
  initAndStart: (videoEl: HTMLVideoElement, overlayCanvas?: HTMLCanvasElement | null, modeOverride?: TrackingMode) => Promise<void>;
  stopTracking: () => void;
}

export function useTracking(): TrackingHook {
  const [trackingMode, setTrackingMode] = useState<TrackingMode>('HEAD');
  const [trackingState, setTrackingState] = useState<TrackingState>('IDLE');
  const [trackingError, setTrackingError] = useState<string | null>(null);
  const [gestureMode, setGestureMode] = useState<GestureMode>('NONE');

  const latestPositionRef = useRef<HeadPosition | null>(null);
  const latestGestureRef  = useRef<GestureResult | null>(null);
  const trackerRef        = useRef<FaceTracker | HandTracker | null>(null);

  const initAndStart = useCallback(async (
    videoEl: HTMLVideoElement,
    overlayCanvas?: HTMLCanvasElement | null,
    modeOverride?: TrackingMode
  ) => {
    // Dispose any running tracker before creating a new one
    if (trackerRef.current) {
      trackerRef.current.dispose();
      trackerRef.current = null;
    }

    const onState = (state: TrackingState, error?: string) => {
      setTrackingState(state);
      setTrackingError(error ?? null);
    };

    const activeMode = modeOverride || trackingMode;

    if (activeMode === 'HEAD') {
      const onGesture = (result: GestureResult) => {
        latestPositionRef.current = result.position;
        latestGestureRef.current  = result;
        setGestureMode(result.mode);
      };
      const tracker = new FaceTracker(onGesture, onState);
      if (overlayCanvas) tracker.setOverlayCanvas(overlayCanvas);
      trackerRef.current = tracker;
      await tracker.init();
      if (trackerRef.current === tracker) tracker.start(videoEl);

    } else {
      // HAND mode — gesture state machine
      const onGesture = (result: GestureResult) => {
        latestPositionRef.current = result.position;
        latestGestureRef.current  = result;
        setGestureMode(result.mode);
      };

      const tracker = new HandTracker(onGesture, onState);
      if (overlayCanvas) tracker.setOverlayCanvas(overlayCanvas);
      trackerRef.current = tracker;
      await tracker.init();
      if (trackerRef.current === tracker) tracker.start(videoEl);
    }
  }, [trackingMode]);

  const stopTracking = useCallback(() => {
    if (trackerRef.current) {
      trackerRef.current.dispose();
      trackerRef.current = null;
    }
    latestPositionRef.current = null;
    latestGestureRef.current  = null;
    setTrackingState('IDLE');
    setTrackingError(null);
    setGestureMode('NONE');
  }, []);

  return {
    trackingMode,
    setTrackingMode,
    trackingState,
    trackingError,
    gestureMode,
    latestPositionRef,
    latestGestureRef,
    initAndStart,
    stopTracking,
  };
}
