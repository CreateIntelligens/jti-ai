import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';

import MergedCsvPane from '../../src/components/_shared/qaKnowledgeWorkspace/detail/MergedCsvPane';
import type { QaWorkspaceApiClient } from '../../src/components/_shared/qaKnowledgeWorkspace/QaKnowledgeWorkspace';

afterEach(() => {
  cleanup();
});

type MergedCsvApi = Pick<QaWorkspaceApiClient, 'getTopicMergedCsv'>;

function renderPane(api: MergedCsvApi, refreshKey: number) {
  return (
    <MergedCsvPane
      topicId="ortho/prp"
      topicLabel="PRP"
      language="zh"
      availableImages={[]}
      statusMessage={null}
      api={api as QaWorkspaceApiClient}
      refreshKey={refreshKey}
    />
  );
}

describe('MergedCsvPane refresh behavior', () => {
  it('reloads the selected topic when the workspace refresh key changes', async () => {
    const getTopicMergedCsv = vi.fn()
      .mockResolvedValueOnce({
        rows: [{ index: '1', q: '舊問題', a: '舊答案', img: '' }],
        source_files: ['old.csv'],
      })
      .mockResolvedValueOnce({
        rows: [{ index: '1', q: '新問題', a: '新答案', img: '' }],
        source_files: ['new.csv'],
      });
    const api = { getTopicMergedCsv };

    const { rerender } = render(renderPane(api, 0));

    expect(await screen.findByText('舊問題')).toBeTruthy();

    rerender(renderPane(api, 1));

    await waitFor(() => expect(getTopicMergedCsv).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('新問題')).toBeTruthy();
    expect(screen.queryByText('舊問題')).toBeNull();
  });
});
