/**
 * settings.ts — All persisted user preferences for IntentLock.
 *
 * Privacy contract:
 *  • Only non-sensitive UI preferences are stored here.
 *  • No camera frames, face/hand landmarks, biometric identity data,
 *    voice audio, dictated text, or full browsing URLs are written.
 *  • Calibration stores only a normalised head-position offset (two numbers),
 *    not any image, mesh, or identity-linked data.
 *  • All keys are namespaced under SETTINGS_KEY in chrome.storage.local.
 *  • Defaults below are the single source of truth — always merged first.
 *
 * Module responsibilities:
 *  • IntentLockSettings interface: typed schema for all preferences.
 *  • DEFAULT_SETTINGS: fallback values used on first run or after reset.
 *  • validateSettings(): coerce/clamp raw storage data into safe ranges.
 *  • loadSettings / saveSettings / clearSettings: chrome.storage.local I/O.
 */

export const SETTINGS_KEY = 'intentlock_settings_v1';

export interface IntentLockSettings {
  // ── Tracking ──────────────────────────────────────────────────────
  /** Movement mode: 'HEAD' uses the nose-tip landmark; 'HAND' uses wrist */
  trackingMode: 'HEAD' | 'HAND';

  // ── Cursor behaviour ──────────────────────────────────────────────
  /** Cursor sensitivity multiplier (1–10) */
  sensitivity: number;
  /** EMA smoothing alpha (0.05–0.5) — lower value = smoother but laggier */
  smoothAlpha: number;

  // ── Calibration ───────────────────────────────────────────────────
  /**
   * Persisted neutral head position (normalised 0–1 frame coords).
   * Stored so the user does not need to re-calibrate after reopening the panel.
   * Contains ONLY two floating-point numbers — no image, mesh, or identity data.
   * null when no calibration has been saved.
   */
  calibrationNeutral: { x: number; y: number } | null;

  // ── Dwell-to-click ────────────────────────────────────────────────
  /** Whether dwell-to-click is enabled */
  dwellEnabled: boolean;
  /** Dwell hold duration in milliseconds (500–3000) */
  dwellMs: number;

  // ── Safety ────────────────────────────────────────────────────────
  /** Whether IntentShield shows a confirmation prompt for high-impact actions */
  shieldConfirmEnabled: boolean;

  // ── Analytics ─────────────────────────────────────────────────────
  /** Maximum number of session summaries to retain in local storage (5–200) */
  maxSessionHistory: number;
}

export const DEFAULT_SETTINGS: Readonly<IntentLockSettings> = {
  trackingMode:          'HEAD',
  sensitivity:           4,
  smoothAlpha:           0.18,
  calibrationNeutral:    null,
  dwellEnabled:          false,
  dwellMs:               1200,
  shieldConfirmEnabled:  true,
  maxSessionHistory:     50,
};

/** Validation: clamp/coerce raw values into safe ranges. */
export function validateSettings(raw: Partial<IntentLockSettings>): IntentLockSettings {
  const d = DEFAULT_SETTINGS;

  // Validate calibrationNeutral: only accept a plain {x, y} object with numeric values in [0,1].
  // Any malformed or out-of-range value is treated as null (re-calibrate next session).
  let calNeutral: { x: number; y: number } | null = null;
  const rawCal = raw.calibrationNeutral;
  if (
    rawCal !== null &&
    typeof rawCal === 'object' &&
    typeof (rawCal as any).x === 'number' &&
    typeof (rawCal as any).y === 'number' &&
    isFinite((rawCal as any).x) && isFinite((rawCal as any).y) &&
    (rawCal as any).x >= 0 && (rawCal as any).x <= 1 &&
    (rawCal as any).y >= 0 && (rawCal as any).y <= 1
  ) {
    calNeutral = { x: (rawCal as any).x, y: (rawCal as any).y };
  }

  return {
    trackingMode:         raw.trackingMode === 'HAND' ? 'HAND' : 'HEAD',
    sensitivity:          clamp(Number(raw.sensitivity ?? d.sensitivity), 1, 10),
    smoothAlpha:          clamp(Number(raw.smoothAlpha ?? d.smoothAlpha), 0.05, 0.5),
    calibrationNeutral:   calNeutral,
    dwellEnabled:         Boolean(raw.dwellEnabled ?? d.dwellEnabled),
    dwellMs:              clamp(Number(raw.dwellMs ?? d.dwellMs), 500, 3000),
    shieldConfirmEnabled: Boolean(raw.shieldConfirmEnabled ?? d.shieldConfirmEnabled),
    maxSessionHistory:    clamp(Number(raw.maxSessionHistory ?? d.maxSessionHistory), 5, 200),
  };
}

function clamp(v: number, lo: number, hi: number) { return Math.max(lo, Math.min(hi, v)); }

/** Load settings from chrome.storage.local, merging over defaults. */
export async function loadSettings(): Promise<IntentLockSettings> {
  return new Promise(resolve => {
    chrome.storage.local.get(SETTINGS_KEY, result => {
      const raw = result[SETTINGS_KEY] ?? {};
      resolve(validateSettings({ ...DEFAULT_SETTINGS, ...raw }));
    });
  });
}

/** Persist current settings to chrome.storage.local. */
export async function saveSettings(s: IntentLockSettings): Promise<void> {
  return new Promise(resolve => {
    chrome.storage.local.set({ [SETTINGS_KEY]: s }, resolve);
  });
}

/** Delete all settings, reverting to defaults on next load. */
export async function clearSettings(): Promise<void> {
  return new Promise(resolve => chrome.storage.local.remove(SETTINGS_KEY, resolve));
}
