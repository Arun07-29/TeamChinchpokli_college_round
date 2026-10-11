import { describe, it, expect, vi } from 'vitest';
import { validateActionPlan } from '../src/services/actionValidator';
import { ActionExecutor } from '../src/services/actionExecutor';

describe('actionValidator', () => {
  it('validates a correct action plan', () => {
    const plan = [
      { type: 'NAVIGATE', url: 'https://youtube.com' },
      { type: 'SCROLL', direction: 'down' }
    ];
    const result = validateActionPlan(plan);
    expect(result.valid).toBe(true);
    expect(result.plan).toEqual(plan);
  });

  it('rejects a malformed plan (not an array)', () => {
    const result = validateActionPlan({ type: 'NAVIGATE' });
    expect(result.valid).toBe(false);
    expect(result.error).toContain('must be an array');
  });

  it('rejects unsupported actions', () => {
    const plan = [{ type: 'HACK_MAINFRAME' }];
    const result = validateActionPlan(plan);
    expect(result.valid).toBe(false);
    expect(result.error).toContain('Unsupported action type');
  });

  it('rejects invalid URLs', () => {
    const plan = [{ type: 'NAVIGATE', url: 'javascript:alert(1)' }];
    const result = validateActionPlan(plan);
    expect(result.valid).toBe(false);
    expect(result.error).toContain('invalid protocol');
  });

  it('rejects missing parameters', () => {
    const plan = [{ type: 'SEARCH' }];
    const result = validateActionPlan(plan);
    expect(result.valid).toBe(false);
    expect(result.error).toContain('missing query string');
  });
});

describe('ActionExecutor', () => {
  it('handles cancellation gracefully', async () => {
    const executor = new ActionExecutor(1);
    const controller = new AbortController();
    
    // Simulate slow progress to allow cancellation
    const progressUpdates: string[] = [];
    const onProgress = (s: string) => progressUpdates.push(s);

    const plan = [
      { type: 'ASK_CLARIFICATION', message: 'Hello' },
      { type: 'ASK_CLARIFICATION', message: 'World' }
    ] as any;

    // Abort immediately
    controller.abort();

    const result = await executor.executePlan(plan, onProgress, controller.signal);
    expect(result.success).toBe(false);
    expect(result.message).toBe('Execution cancelled.');
    expect(progressUpdates.length).toBe(0); // Cancelled before first step
  });
});
