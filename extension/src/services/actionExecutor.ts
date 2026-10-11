import type { ActionPlan, BrowserAction, MessageType } from '../shared/types';

export interface ActionExecutionResult {
  success: boolean;
  message: string;
}

export type ActionProgressCallback = (status: string) => void;

export class ActionExecutor {
  private tabId: number | null;

  constructor(tabId: number | null) {
    this.tabId = tabId;
  }

  async executePlan(
    plan: ActionPlan, 
    onProgress: ActionProgressCallback, 
    signal: AbortSignal
  ): Promise<ActionExecutionResult> {
    for (let i = 0; i < plan.length; i++) {
      if (signal.aborted) {
        return { success: false, message: 'Execution cancelled.' };
      }
      const action = plan[i];
      try {
        const result = await this.executeAction(action, onProgress, signal);
        if (!result.success) {
          return { success: false, message: `Failed at step ${i + 1}: ${result.message}` };
        }
      } catch (err: any) {
        return { success: false, message: `Error at step ${i + 1}: ${err.message}` };
      }
    }
    return { success: true, message: 'Plan executed successfully.' };
  }

  private executeAction(
    action: BrowserAction, 
    onProgress: ActionProgressCallback,
    signal: AbortSignal
  ): Promise<ActionExecutionResult> {
    return new Promise((resolve) => {
      if (signal.aborted) return resolve({ success: false, message: 'Cancelled.' });

      // ── NAVIGATE: update the CURRENT tab (not open a new one) ──────────────
      if (action.type === 'NAVIGATE') {
        onProgress(`Going to ${action.url}...`);
        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
          const activeTab = tabs[0];
          if (!activeTab?.id) return resolve({ success: false, message: 'No active tab found.' });
          chrome.tabs.update(activeTab.id, { url: action.url }, () => {
            if (chrome.runtime.lastError) {
              resolve({ success: false, message: chrome.runtime.lastError.message || 'Navigation failed' });
            } else {
              resolve({ success: true, message: 'Navigation started.' });
            }
          });
        });
      }

      // ── SEARCH: open Google search in current tab ────────────────────────────
      else if (action.type === 'SEARCH') {
        onProgress(`Searching for "${action.query}"...`);
        const searchUrl = 'https://www.google.com/search?q=' + encodeURIComponent(action.query);
        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
          const activeTab = tabs[0];
          if (!activeTab?.id) return resolve({ success: false, message: 'No active tab found.' });
          chrome.tabs.update(activeTab.id, { url: searchUrl }, () => {
            if (chrome.runtime.lastError) resolve({ success: false, message: 'Search failed' });
            else resolve({ success: true, message: 'Search started.' });
          });
        });
      }

      // ── CLOSE_TAB ────────────────────────────────────────────────────────────
      else if (action.type === 'CLOSE_TAB') {
        onProgress('Closing current tab...');
        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
          if (tabs[0]?.id) {
            chrome.tabs.remove(tabs[0].id, () => resolve({ success: true, message: 'Tab closed.' }));
          } else {
            resolve({ success: false, message: 'No active tab found.' });
          }
        });
      }

      // ── NEW_TAB: explicitly open a new tab ──────────────────────────────────
      else if (action.type === 'NEW_TAB') {
        onProgress('Opening new tab...');
        chrome.tabs.create({ url: action.url ?? 'https://www.google.com' }, () =>
          resolve({ success: true, message: 'New tab opened.' })
        );
      }

      // ── NEXT_TAB ─────────────────────────────────────────────────────────────
      else if (action.type === 'NEXT_TAB') {
        onProgress('Switching to next tab...');
        chrome.tabs.query({ currentWindow: true }, (tabs) => {
          const active = tabs.findIndex(t => t.active);
          const next = tabs[(active + 1) % tabs.length];
          if (next?.id) chrome.tabs.update(next.id, { active: true }, () => resolve({ success: true, message: 'Switched to next tab.' }));
          else resolve({ success: false, message: 'Could not switch tab.' });
        });
      }

      // ── PREV_TAB ─────────────────────────────────────────────────────────────
      else if (action.type === 'PREV_TAB') {
        onProgress('Switching to previous tab...');
        chrome.tabs.query({ currentWindow: true }, (tabs) => {
          const active = tabs.findIndex(t => t.active);
          const prev = tabs[(active - 1 + tabs.length) % tabs.length];
          if (prev?.id) chrome.tabs.update(prev.id, { active: true }, () => resolve({ success: true, message: 'Switched to previous tab.' }));
          else resolve({ success: false, message: 'Could not switch tab.' });
        });
      }

      // ── ASK_CLARIFICATION / REPLY: display message, no browser action ─────
      else if (action.type === 'ASK_CLARIFICATION' || (action as any).type === 'REPLY') {
        // These should be handled upstream in ChatInterface, but handle defensively
        resolve({ success: true, message: (action as any).message || '' });
      }

      // ── Content-script actions (scroll, click, type, etc.) ─────────────────
      else {
        const executeOnTab = (targetTabId: number) => {
          // IDENTIFY_ELEMENTS
          if (action.type === 'IDENTIFY_ELEMENTS') {
            onProgress('Identifying elements...');
            chrome.tabs.sendMessage(targetTabId, { type: 'TARGETING_ENABLE' } as MessageType, () => {
              if (chrome.runtime.lastError) resolve({ success: false, message: 'Failed to communicate with tab.' });
              else resolve({ success: true, message: 'Elements identified.' });
            });
            return;
          }

          let cmd = '';
          let arg: string | undefined = undefined;

          if (action.type === 'SCROLL') {
            onProgress(`Scrolling ${action.direction}...`);
            cmd = `SCROLL_${action.direction.toUpperCase()}`;
          } else if (action.type === 'HISTORY') {
            onProgress(`Going ${action.direction}...`);
            cmd = `GO_${action.direction.toUpperCase()}`;
          } else if (action.type === 'FOCUS_FIELD') {
            onProgress(`Focusing field ${action.nameOrId}...`);
            cmd = 'FOCUS';
            arg = action.nameOrId;
          } else if (action.type === 'CLICK_ELEMENT') {
            onProgress(`Clicking ${action.nameOrId}...`);
            cmd = 'CLICK_TEXT';
            arg = action.nameOrId;
          } else if (action.type === 'INSERT_TEXT') {
            onProgress(`Typing text...`);
            cmd = 'TYPE';
            arg = action.text;
          }

          if (cmd) {
            const msg: MessageType = { type: 'VOICE_COMMAND', command: cmd, arg };
            chrome.tabs.sendMessage(targetTabId, msg, async (response) => {
              if (chrome.runtime.lastError) {
                // Try dynamic injection retry if script was not yet present
                try {
                  await chrome.scripting.executeScript({
                    target: { tabId: targetTabId },
                    files: ['assets/content.js']
                  });
                  chrome.tabs.sendMessage(targetTabId, msg, (retryResponse) => {
                    if (chrome.runtime.lastError) {
                      resolve({ success: false, message: 'Cannot control this page (restricted by Chrome policy or internal page).' });
                    } else if (retryResponse && !retryResponse.success) {
                      resolve({ success: false, message: 'Action failed in tab.' });
                    } else {
                      resolve({ success: true, message: 'Success' });
                    }
                  });
                } catch {
                  resolve({ success: false, message: 'Cannot control this page (restricted by Chrome policy).' });
                }
              } else if (response && !response.success) {
                resolve({ success: false, message: 'Action failed in tab.' });
              } else {
                resolve({ success: true, message: 'Success' });
              }
            });
          } else {
            resolve({ success: false, message: `Unsupported action type: ${action.type}` });
          }
        };

        if (this.tabId) {
          executeOnTab(this.tabId);
        } else {
          chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
            const currentTabId = tabs[0]?.id;
            if (currentTabId) {
              executeOnTab(currentTabId);
            } else {
              resolve({ success: false, message: 'No active tab to execute action.' });
            }
          });
        }
      }
    });
  }
}
