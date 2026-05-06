import { afterEach, describe, expect, it, vi } from 'vitest';

import { listHciotTopics, listHciotTopicsAdmin } from '../../src/services/api/hciot';

describe('HCIoT topic API paths', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  function stubSuccessfulFetch() {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ categories: [] }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('localStorage', {
      getItem: () => null,
      setItem: () => {},
      removeItem: () => {},
    });
    return fetchMock;
  }

  it('loads public topics with language in the path', async () => {
    const fetchMock = stubSuccessfulFetch();

    await listHciotTopics('en');

    expect(fetchMock).toHaveBeenCalledWith('/api/hciot/topics/en', expect.any(Object));
  });

  it('loads admin topic metadata with language in the path', async () => {
    const fetchMock = stubSuccessfulFetch();

    await listHciotTopicsAdmin('en');

    expect(fetchMock).toHaveBeenCalledWith('/api/hciot-admin/topics/en', {});
  });
});
