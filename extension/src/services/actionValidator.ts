import type { ActionPlan } from '../shared/types';

export function validateActionPlan(plan: any): { valid: boolean; plan?: ActionPlan; error?: string } {
  if (!Array.isArray(plan)) {
    return { valid: false, error: 'Plan must be an array of actions.' };
  }

  for (let i = 0; i < plan.length; i++) {
    const action = plan[i];
    if (typeof action !== 'object' || action === null) {
      return { valid: false, error: `Action at index ${i} is not a valid object.` };
    }
    
    // Type checking for specific actions
    switch (action.type) {
      case 'NAVIGATE':
        if (typeof action.url !== 'string') return { valid: false, error: `NAVIGATE action at index ${i} missing url string.` };
        if (
          !action.url.startsWith('http://') &&
          !action.url.startsWith('https://') &&
          !action.url.startsWith('chrome://') &&
          !action.url.startsWith('about:') &&
          !action.url.startsWith('file://')
        ) {
          return { valid: false, error: `NAVIGATE action at index ${i} uses an invalid protocol.` };
        }
        break;
      case 'SEARCH':
        if (typeof action.query !== 'string') return { valid: false, error: `SEARCH action at index ${i} missing query string.` };
        break;
      case 'SCROLL':
        if (!['up', 'down', 'top', 'bottom'].includes(action.direction)) {
          return { valid: false, error: `SCROLL action at index ${i} has invalid direction.` };
        }
        break;
      case 'HISTORY':
        if (!['back', 'forward'].includes(action.direction)) {
          return { valid: false, error: `HISTORY action at index ${i} has invalid direction.` };
        }
        break;
      case 'IDENTIFY_ELEMENTS':
        break;
      case 'FOCUS_FIELD':
        if (typeof action.nameOrId !== 'string') return { valid: false, error: `FOCUS_FIELD action at index ${i} missing nameOrId string.` };
        break;
      case 'INSERT_TEXT':
        if (typeof action.text !== 'string') return { valid: false, error: `INSERT_TEXT action at index ${i} missing text string.` };
        break;
      case 'CLICK_ELEMENT':
        if (typeof action.nameOrId !== 'string') return { valid: false, error: `CLICK_ELEMENT action at index ${i} missing nameOrId string.` };
        break;
      case 'ASK_CLARIFICATION':
        if (typeof action.message !== 'string') return { valid: false, error: `ASK_CLARIFICATION action at index ${i} missing message string.` };
        break;
      case 'REPLY':
        if (typeof action.message !== 'string') return { valid: false, error: `REPLY action at index ${i} missing message string.` };
        break;
      case 'CLOSE_TAB':
      case 'NEXT_TAB':
      case 'PREV_TAB':
        break; // no params needed
      case 'NEW_TAB':
        // url is optional, but if provided must be a valid protocol
        if (action.url !== undefined && typeof action.url === 'string') {
          if (
            !action.url.startsWith('http://') &&
            !action.url.startsWith('https://') &&
            !action.url.startsWith('chrome://') &&
            !action.url.startsWith('about:') &&
            !action.url.startsWith('file://')
          ) {
            return { valid: false, error: `NEW_TAB action at index ${i} url must use a valid protocol.` };
          }
        }
        break;
      default:
        return { valid: false, error: `Unsupported action type '${action.type}' at index ${i}.` };
    }
  }

  return { valid: true, plan: plan as ActionPlan };
}
