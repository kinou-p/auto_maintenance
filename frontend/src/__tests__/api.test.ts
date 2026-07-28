// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { setGlobalErrorHandler } from '../lib/api';

describe('api helper module', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('allows registering a global error handler', () => {
    const handler = vi.fn();
    setGlobalErrorHandler(handler);
    expect(handler).not.toHaveBeenCalled();
  });
});
