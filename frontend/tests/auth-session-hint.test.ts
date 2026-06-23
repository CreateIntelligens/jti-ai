import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getMe, login, logout } from '../src/services/api/auth';

const SESSION_HINT_KEY = 'jtai:auth-session-known';

describe('auth session hint', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('remembers that this browser has a session after login succeeds', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ token: 'jwt', role: 'admin', scope: null }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await login('alice', 'pw');

    expect(window.localStorage.getItem(SESSION_HINT_KEY)).toBe('1');
  });

  it('clears the browser session hint when profile lookup is unauthorized', async () => {
    window.localStorage.setItem(SESSION_HINT_KEY, '1');
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Missing session token or authorization credentials' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await expect(getMe()).rejects.toThrow('Missing session token or authorization credentials');

    expect(window.localStorage.getItem(SESSION_HINT_KEY)).toBeNull();
  });

  it('clears the browser session hint even when logout request fails', async () => {
    window.localStorage.setItem(SESSION_HINT_KEY, '1');
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('network down'));

    await expect(logout()).rejects.toThrow('network down');

    expect(window.localStorage.getItem(SESSION_HINT_KEY)).toBeNull();
  });
});
