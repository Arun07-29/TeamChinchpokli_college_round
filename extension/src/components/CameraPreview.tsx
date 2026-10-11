import { useState, useRef, useEffect, useCallback } from 'react';

type CameraState = 'NOT_STARTED' | 'REQUESTING' | 'READY' | 'DENIED' | 'ERROR';

interface Props {
  /** Parent passes a ref so HandTracker/FaceTracker can read video frames */
  videoElRef?: React.MutableRefObject<HTMLVideoElement | null>;
  /** Callback fired when camera becomes ready or stops */
  onCameraReady?: (isReady: boolean) => void;
  /**
   * When true, the camera stream is NOT stopped when this component unmounts.
   * Use this while a session is active so closing the panel doesn't kill tracking.
   */
  keepAlive?: boolean;
  /** Callback that fires with the canvas element used for landmark overlay drawing */
  onCanvasReady?: (canvas: HTMLCanvasElement | null) => void;
}

export function CameraPreview({ videoElRef, onCameraReady, keepAlive, onCanvasReady }: Props) {
  const [cameraState, setCameraState] = useState<CameraState>('NOT_STARTED');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const internalRef  = useRef<HTMLVideoElement>(null);
  const canvasRef    = useRef<HTMLCanvasElement>(null);
  const streamRef    = useRef<MediaStream | null>(null);
  const permTabIdRef = useRef<number | null>(null);
  const keepAliveRef = useRef(keepAlive);

  // Keep ref in sync so cleanup callback sees the latest value without stale closure
  useEffect(() => { keepAliveRef.current = keepAlive; }, [keepAlive]);

  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    const el = internalRef.current;
    if (el) el.srcObject = null;
    if (videoElRef) videoElRef.current = null;
    setCameraState('NOT_STARTED');
    setErrorMessage(null);
    if (onCameraReady) onCameraReady(false);
    if (onCanvasReady) onCanvasReady(null);
  }, [videoElRef, onCameraReady, onCanvasReady]);

  const openPermissionsTab = useCallback(() => {
    setErrorMessage('Click "Grant Camera & Microphone Access" in the tab that opened, then click Allow.');
    chrome.tabs.create(
      { url: chrome.runtime.getURL('permissions.html') },
      (tab) => { permTabIdRef.current = tab.id ?? null; }
    );
  }, []);

  const startCamera = useCallback(async () => {
    try {
      setCameraState('REQUESTING');
      setErrorMessage(null);
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: 'user' },
        audio: true,
      });
      streamRef.current = stream;

      const el = internalRef.current;
      if (el) {
        el.srcObject = stream;
        el.play().catch(e => console.error('Video play error:', e));
        if (videoElRef) videoElRef.current = el;
      }
      setCameraState('READY');
      if (onCameraReady) onCameraReady(true);
      // Notify parent about the canvas for landmark drawing
      if (onCanvasReady && canvasRef.current) onCanvasReady(canvasRef.current);
    } catch (err: unknown) {
      const name = (err as DOMException).name;
      if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
        setCameraState('DENIED');
        setErrorMessage(null);
      } else if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
        setCameraState('ERROR');
        setErrorMessage('No camera found on this device.');
      } else {
        setCameraState('ERROR');
        setErrorMessage((err instanceof Error ? err.message : null) || 'Failed to start camera.');
      }
    }
  }, [videoElRef, onCameraReady, onCanvasReady]);

  // Auto-retry when permissions tab closes
  useEffect(() => {
    const onRemoved = (tabId: number) => {
      if (tabId === permTabIdRef.current) {
        permTabIdRef.current = null;
        setTimeout(() => startCamera(), 400);
      }
    };
    chrome.tabs.onRemoved.addListener(onRemoved);
    return () => chrome.tabs.onRemoved.removeListener(onRemoved);
  }, [startCamera]);

  // Auto-start camera when mounted (if not already started)
  useEffect(() => {
    if (cameraState === 'NOT_STARTED') startCamera();
  }, [cameraState, startCamera]);

  // Cleanup on unmount — only stop camera if keepAlive is false
  useEffect(() => {
    return () => {
      if (!keepAliveRef.current) {
        stopCamera();
      }
      // If keepAlive, leave stream running — only detach from DOM element
    };
  }, [stopCamera]);

  const statusColor = () => {
    switch (cameraState) {
      case 'READY':      return '#28a745';
      case 'REQUESTING': return '#ffc107';
      case 'DENIED':
      case 'ERROR':      return '#dc3545';
      default:           return '#6c757d';
    }
  };

  const statusText = () => {
    switch (cameraState) {
      case 'NOT_STARTED': return 'Starting…';
      case 'REQUESTING':  return 'Requesting Permission…';
      case 'READY':       return 'Camera Ready';
      case 'DENIED':      return 'Permission Required';
      case 'ERROR':       return 'Error';
    }
  };

  return (
    <div style={{ marginTop: '12px' }}>
      {/* Status row */}
      <div className="info-row" style={{ marginBottom: '8px' }}>
        <span className="info-label" style={{ fontWeight: 600 }}>Camera Status:</span>
        <span style={{ fontWeight: 500, color: statusColor() }}>{statusText()}</span>
      </div>

      {/* Error / hint */}
      {errorMessage && (
        <div style={{ color: '#555', fontSize: '12px', marginBottom: '8px', lineHeight: 1.4, backgroundColor: '#fff3cd', padding: '8px', borderRadius: '4px', border: '1px solid #ffc107' }}>
          {errorMessage}
        </div>
      )}

      {/* Preview box — video + canvas overlay stacked */}
      <div style={{ width: '100%', height: '160px', backgroundColor: '#1a1a2e', borderRadius: '8px', overflow: 'hidden', position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '10px', border: '1px solid #333' }}>
        {cameraState !== 'READY' && (
          <div style={{ color: '#555', fontSize: '24px', zIndex: 1 }}>📷</div>
        )}
        {/* Video element always in DOM so ref is always valid */}
        <video
          ref={internalRef}
          muted
          playsInline
          style={{
            position: 'absolute', inset: 0,
            width: '100%', height: '100%',
            objectFit: 'cover',
            transform: 'scaleX(-1)',
            display: cameraState === 'READY' ? 'block' : 'none',
          }}
        />
        {/* Canvas overlay for landmark drawing — same dimensions, pointer-events:none */}
        <canvas
          ref={canvasRef}
          style={{
            position: 'absolute', inset: 0,
            width: '100%', height: '100%',
            pointerEvents: 'none',
            display: cameraState === 'READY' ? 'block' : 'none',
          }}
        />
      </div>

      {/* Controls */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {cameraState === 'DENIED' && (
          <>
            <button className="primary" onClick={openPermissionsTab}>Grant Camera &amp; Microphone Access</button>
            <div style={{ fontSize: '11px', color: '#888', textAlign: 'center' }}>
              A tab will open — click Allow, then it starts automatically.
            </div>
          </>
        )}
      </div>
    </div>
  );
}
