export type MessageType =
  | { type: 'ACTIVATE_SESSION' }
  | { type: 'DEACTIVATE_SESSION' }
  | { type: 'SESSION_STATUS_QUERY' }
  | { type: 'SESSION_STATUS_RESPONSE'; isActive: boolean }
  | { type: 'CURSOR_MOVE'; x: number; y: number; gesture?: string }   // 0..1 normalised viewport coords
  | { type: 'CURSOR_HIDE' }
  | { type: 'CURSOR_SHOW' }
  | { type: 'VOICE_COMMAND'; command: string; arg?: string }
  | { type: 'PINCH_CLICK' }           // click element at current virtual cursor position
  | { type: 'SCROLL_DELTA'; delta: number }  // scroll page by normalised delta
  // ── Targeting (PROMPT 8) ──────────────────────────────────────
  | { type: 'TARGETING_ENABLE' }
  | { type: 'TARGETING_DISABLE' }
  | { type: 'TARGETING_SELECT_NUMBER'; n: number }
  | { type: 'TARGETING_SELECT_NAME'; name: string }
  // ── IntentShield (PROMPT 9) ───────────────────────────────────
  | { type: 'SHIELD_PAUSE' }
  | { type: 'SHIELD_RESUME' }
  | { type: 'DWELL_CLICK'; x: number; y: number }
  | { type: 'CONFIRM_ACTION'; actionId: string };

// ── Action Schema (PROMPT B) ───────────────────────────────────
export type BrowserAction =
  | { type: 'NAVIGATE'; url: string }
  | { type: 'SEARCH'; query: string }
  | { type: 'SCROLL'; direction: 'up' | 'down' | 'top' | 'bottom'; amount?: string }
  | { type: 'HISTORY'; direction: 'back' | 'forward' }
  | { type: 'IDENTIFY_ELEMENTS' }
  | { type: 'FOCUS_FIELD'; nameOrId: string }
  | { type: 'INSERT_TEXT'; text: string }
  | { type: 'CLICK_ELEMENT'; nameOrId: string }
  | { type: 'ASK_CLARIFICATION'; message: string }
  | { type: 'CLOSE_TAB' }
  | { type: 'NEW_TAB'; url?: string }
  | { type: 'NEXT_TAB' }
  | { type: 'PREV_TAB' };

export type ActionPlan = BrowserAction[];
