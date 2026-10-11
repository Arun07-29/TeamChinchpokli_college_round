/**
 * analytics.ts — Local session-event model for IntentLock.
 *
 * Privacy contract:
 *  • Only aggregate counts and timestamps are stored.
 *  • Raw camera frames, face/hand landmarks, voice audio, dictated text,
 *    and full browsing URLs are NEVER written here.
 *  • Session summaries are retained locally up to maxSessionHistory entries.
 */

export const ANALYTICS_KEY = 'intentlock_analytics_v1';

export type CommandCategory =
  | 'scroll'
  | 'navigate'
  | 'voice_select'
  | 'targeting'
  | 'dwell'
  | 'session'
  | 'other';

export interface CommandEvent {
  category: CommandCategory;
  command: string;   // e.g. 'SCROLL_DOWN', 'CLICK_TEXT'  — NO transcribed text
  success: boolean;
}

export interface SessionSummary {
  id: string;
  startedAt: number;   // Unix ms
  endedAt: number | null;
  durationMs: number | null;
  trackingMode: 'HEAD' | 'HAND';
  commandCounts: Record<string, number>;   // command → count
  successCount: number;
  failureCount: number;
  cancelCount: number;
}

// ── In-memory current session ────────────────────────────────────────────────

let currentSession: SessionSummary | null = null;

export function startSession(trackingMode: 'HEAD' | 'HAND'): SessionSummary {
  currentSession = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    startedAt: Date.now(),
    endedAt: null,
    durationMs: null,
    trackingMode,
    commandCounts: {},
    successCount: 0,
    failureCount: 0,
    cancelCount: 0,
  };
  return currentSession;
}

export function recordCommand(event: CommandEvent) {
  if (!currentSession) return;
  const key = event.command;
  currentSession.commandCounts[key] = (currentSession.commandCounts[key] ?? 0) + 1;
  if (event.success) currentSession.successCount++;
  else currentSession.failureCount++;
}

export function recordCancel() {
  if (!currentSession) return;
  currentSession.cancelCount++;
}

export function getCurrentSession(): SessionSummary | null {
  return currentSession;
}

// ── Persistence ───────────────────────────────────────────────────────────────

export async function endAndSaveSession(maxHistory: number): Promise<void> {
  if (!currentSession) return;
  const now = Date.now();
  currentSession.endedAt = now;
  currentSession.durationMs = now - currentSession.startedAt;
  const snapshot = { ...currentSession };
  currentSession = null;

  const history = await loadHistory();
  history.unshift(snapshot);                          // newest first
  const trimmed = history.slice(0, maxHistory);       // cap to limit
  await saveHistory(trimmed);
}

export async function loadHistory(): Promise<SessionSummary[]> {
  return new Promise(resolve => {
    chrome.storage.local.get(ANALYTICS_KEY, result => {
      resolve(Array.isArray(result[ANALYTICS_KEY]) ? result[ANALYTICS_KEY] : []);
    });
  });
}

async function saveHistory(history: SessionSummary[]): Promise<void> {
  return new Promise(resolve => chrome.storage.local.set({ [ANALYTICS_KEY]: history }, resolve));
}

export async function clearHistory(): Promise<void> {
  currentSession = null;
  return new Promise(resolve => chrome.storage.local.remove(ANALYTICS_KEY, resolve));
}

// ── Helpers ───────────────────────────────────────────────────────────────────

export function categorise(command: string): CommandCategory {
  if (command.startsWith('SCROLL'))  return 'scroll';
  if (command === 'GO_BACK' || command === 'GO_FORWARD') return 'navigate';
  if (command.startsWith('CLICK') || command === 'FOCUS' || command === 'TYPE') return 'voice_select';
  if (command.startsWith('SELECT') || command.startsWith('TARGETING')) return 'targeting';
  if (command === 'DWELL_CLICK') return 'dwell';
  if (command === 'STOP_SESSION' || command === 'PAUSE_CONTROLS' || command === 'RESUME_CONTROLS') return 'session';
  return 'other';
}
