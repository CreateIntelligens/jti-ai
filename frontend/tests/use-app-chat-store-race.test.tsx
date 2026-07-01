import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { StartChatResponse, Store } from '../src/types';

const apiMocks = vi.hoisted(() => ({
  fetchStores: vi.fn(),
  getKeyInfos: vi.fn(),
  listManagedKnowledgeFiles: vi.fn(),
  startChat: vi.fn(),
}));

vi.mock('../src/services/api', () => apiMocks);

import { useAppChat } from '../src/hooks/useAppChat';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('useAppChat store switching', () => {
  const stores: Store[] = [
    {
      name: '__esg__',
      display_name: 'ESG 中文',
      managed_app: 'esg',
      managed_language: 'zh',
    },
    {
      name: '__esg__en',
      display_name: 'ESG English',
      managed_app: 'esg',
      managed_language: 'en',
    },
  ];

  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    apiMocks.fetchStores.mockResolvedValue(stores);
    apiMocks.getKeyInfos.mockResolvedValue({ count: 0, names: [] });
    apiMocks.listManagedKnowledgeFiles.mockResolvedValue({ files: [] });
  });

  it('ignores a stale startChat response from a previously selected store', async () => {
    localStorage.setItem('lastKnowledgeTargetId', '__esg__');

    const initialZh = deferred<StartChatResponse>();
    const lateZh = deferred<StartChatResponse>();
    const en = deferred<StartChatResponse>();
    const starts: Record<string, Array<ReturnType<typeof deferred<StartChatResponse>>>> = {
      __esg__: [initialZh, lateZh],
      __esg__en: [en],
    };

    apiMocks.startChat.mockImplementation((storeName: string) => {
      const next = starts[storeName]?.shift();
      if (!next) throw new Error(`unexpected startChat(${storeName})`);
      return next.promise;
    });

    const { result } = renderHook(() => useAppChat(false));

    initialZh.resolve({ session_id: 'session-zh-initial' });
    await waitFor(() => expect(result.current.sessionId).toBe('session-zh-initial'));

    act(() => {
      void result.current.handleStoreChange('__esg__');
    });
    await waitFor(() => expect(apiMocks.startChat).toHaveBeenCalledTimes(2));

    act(() => {
      void result.current.handleStoreChange('__esg__en');
    });
    await waitFor(() => expect(apiMocks.startChat).toHaveBeenCalledTimes(3));

    await act(async () => {
      en.resolve({ session_id: 'session-en' });
      await en.promise;
    });
    await waitFor(() => expect(result.current.sessionId).toBe('session-en'));

    await act(async () => {
      lateZh.resolve({ session_id: 'session-zh-late' });
      await lateZh.promise;
    });

    expect(result.current.currentStore).toBe('__esg__en');
    expect(result.current.sessionId).toBe('session-en');
  });
});
