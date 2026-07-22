import { afterEach, describe, expect, it, vi } from 'vitest';

import { sendMessage, startChat } from '../src/services/api/general';

function createResponse(data: Record<string, unknown>): Response {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe('General model selection', () => {
  it('uses the latest Flash-Lite alias when no model is stored', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(createResponse({ session_id: 'session-1' }))
      .mockResolvedValueOnce(createResponse({ message: 'answer' }));
    vi.stubGlobal('fetch', fetchMock);

    await startChat('store-a');
    await sendMessage('question', 'session-1');

    const startBody = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body));
    const messageBody = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body));
    expect(startBody.model).toBe('gemini-flash-lite-latest');
    expect(messageBody.model).toBe('gemini-flash-lite-latest');
  });

  it('preserves an explicitly selected model', async () => {
    localStorage.setItem('selectedModel', 'gemini-3.1-flash-lite');
    const fetchMock = vi.fn().mockResolvedValue(createResponse({ session_id: 'session-1' }));
    vi.stubGlobal('fetch', fetchMock);

    await startChat('store-a');

    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body));
    expect(body.model).toBe('gemini-3.1-flash-lite');
  });
});
