import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  getJtiTopicMergedCsv,
  listJtiTopics,
  listJtiTopicsAdmin,
  setJtiCategoryHidden,
} from '../src/services/api/jti';
import {
  getEsgTopicMergedCsv,
  listEsgTopics,
  listEsgTopicsAdmin,
  setEsgCategoryHidden,
} from '../src/services/api/esg';

describe('JTI and ESG topic API paths', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  function stubSuccessfulFetch(body: unknown = { categories: [] }) {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(body), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('localStorage', {
      getItem: () => null,
      setItem: () => {},
      removeItem: () => {},
    });
    return fetchMock;
  }

  it('loads JTI topics through fixed-app public and admin paths', async () => {
    const fetchMock = stubSuccessfulFetch();

    await listJtiTopics('en');
    await listJtiTopicsAdmin('zh');

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/jti/topics/en', expect.any(Object));
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/jti/topics/zh/all', expect.any(Object));
  });

  it('loads ESG topics through fixed-app public and admin paths', async () => {
    const fetchMock = stubSuccessfulFetch();

    await listEsgTopics('en');
    await listEsgTopicsAdmin('zh');

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/esg/topics/en', expect.any(Object));
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/esg/topics/zh/all', expect.any(Object));
  });

  it('updates JTI and ESG category visibility through app-specific admin endpoints', async () => {
    const fetchMock = stubSuccessfulFetch();

    await setJtiCategoryHidden('faq', true, 'zh');
    await setEsgCategoryHidden('environment', false, 'en');

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/jti-admin/topics/categories/zh/faq/visibility', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hidden: true }),
      credentials: 'include',
    });
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/esg-admin/topics/categories/en/environment/visibility', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hidden: false }),
      credentials: 'include',
    });
  });

  it('loads merged CSV rows through app-specific knowledge routers', async () => {
    const fetchMock = stubSuccessfulFetch({ rows: [], source_files: [] });

    await getJtiTopicMergedCsv('faq/general', 'zh');
    await getEsgTopicMergedCsv('environment/green', 'en');

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/jti-admin/knowledge/topic-csv-merged?topic_id=faq%2Fgeneral&language=zh',
      expect.any(Object),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/esg-admin/knowledge/topic-csv-merged?topic_id=environment%2Fgreen&language=en',
      expect.any(Object),
    );
  });
});
