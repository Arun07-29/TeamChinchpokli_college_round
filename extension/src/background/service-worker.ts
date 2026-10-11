/**
 * service-worker.ts — IntentLock background service worker.
 *
 * Responsibilities:
 *  1. Opens the side panel when the toolbar icon is clicked.
 *  2. Handles the CONFIRM_ACTION message forwarded from content scripts.
 *
 * This file is intentionally minimal — all session state, analytics,
 * and preference storage live in the side-panel React app and shared modules.
 */

// Open the side panel on toolbar icon click
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((error: unknown) => console.error('[IntentLock SW] setPanelBehavior failed:', error));

// Handle messages that require cross-context routing
chrome.runtime.onMessage.addListener((message, _sender, _sendResponse) => {
  if (message?.type === 'CONFIRM_ACTION') {
    // CONFIRM_ACTION is currently handled fully within the content script's
    // shadow-DOM confirmation overlay. This branch is reserved for future use
    // (e.g., logging or cross-tab coordination).
  }
});

console.log('[IntentLock] Background service worker running.');
