import type { ActionPlan } from '../shared/types';

export class TestPlanner {
  async generatePlan(prompt: string): Promise<ActionPlan> {
    const text = prompt.toLowerCase();
    
    // Simulate network delay
    await new Promise(r => setTimeout(r, 500));

    if (text.includes('open youtube and search llm')) {
      return [
        { type: 'NAVIGATE', url: 'https://youtube.com' },
        { type: 'FOCUS_FIELD', nameOrId: 'search' },
        { type: 'INSERT_TEXT', text: 'llm from scratch' },
        { type: 'CLICK_ELEMENT', nameOrId: 'search-icon-legacy' }
      ];
    }

    if (text.includes('scroll down a little')) {
      return [
        { type: 'SCROLL', direction: 'down' }
      ];
    }
    
    if (text.includes('go back')) {
      return [
        { type: 'HISTORY', direction: 'back' }
      ];
    }

    if (text.includes('malformed')) {
      // Return invalid plan for testing
      return [
        { type: 'NAVIGATE' } // missing url
      ] as any;
    }

    if (text.includes('unsupported')) {
      return [
        { type: 'HACK_MAINFRAME' }
      ] as any;
    }
    
    if (text.includes('invalid url')) {
      return [
        { type: 'NAVIGATE', url: 'javascript:alert(1)' }
      ];
    }

    if (text.includes('search for')) {
      const q = text.replace('search for', '').trim();
      return [
        { type: 'SEARCH', query: q }
      ];
    }

    // Default fallback
    return [
      { type: 'ASK_CLARIFICATION', message: "I'm a test provider. Say 'scroll down a little' or 'search for cats'." }
    ];
  }
}
