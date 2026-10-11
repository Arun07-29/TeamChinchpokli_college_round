import { describe, it, expect, vi } from 'vitest';
import { GeminiPlanner } from '../src/services/aiPlanner';

// Mock the GoogleGenerativeAI module
vi.mock('@google/generative-ai', () => {
  return {
    GoogleGenerativeAI: class {
      getGenerativeModel() {
        return {
          generateContent: async () => ({
            response: {
              text: () => '[{"type": "SEARCH", "query": "LLM from scratch"}]'
            }
          })
        };
      }
    }
  };
});

describe('GeminiPlanner', () => {
  it('parses AI response correctly into an ActionPlan', async () => {
    const planner = new GeminiPlanner('fake-api-key');
    const plan = await planner.generatePlan('open youtube and search llm from scratch');
    
    expect(Array.isArray(plan)).toBe(true);
    expect(plan.length).toBe(1);
    expect(plan[0].type).toBe('SEARCH');
    expect((plan[0] as any).query).toBe('LLM from scratch');
  });

  it('handles conversational context', async () => {
    const planner = new GeminiPlanner('fake-api-key');
    const plan = await planner.generatePlan('do it', [
      { id: '1', role: 'user', content: 'open youtube and search llm from scratch' },
      { id: '2', role: 'system_event', content: 'Search started.' }
    ]);
    
    expect(Array.isArray(plan)).toBe(true);
  });
});
