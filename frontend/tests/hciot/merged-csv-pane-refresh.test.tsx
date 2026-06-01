import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

import MergedCsvPane from '../../src/components/_shared/qaKnowledgeWorkspace/detail/MergedCsvPane';
import type { QaWorkspaceApiClient } from '../../src/components/_shared/qaKnowledgeWorkspace/QaKnowledgeWorkspace';
import { downloadBlob } from '../../src/utils/download';

vi.mock('../../src/utils/download', () => ({
  downloadBlob: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderPane(
  api: Partial<QaWorkspaceApiClient>,
  refreshKey: number,
  hiddenQuestions?: string[],
) {
  return (
    <MergedCsvPane
      topicId="ortho/prp"
      topicLabel="PRP"
      language="zh"
      availableImages={[]}
      statusMessage={null}
      api={api as QaWorkspaceApiClient}
      refreshKey={refreshKey}
      hiddenQuestions={hiddenQuestions}
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

  it('downloads merged rows with a sequential index and display column', async () => {
    const getTopicMergedCsv = vi.fn().mockResolvedValue({
      rows: [
        { index: '9', q: '顯示題', a: '顯示答', img: '', url: '' },
        { index: '4', q: '隱藏題', a: '隱藏答', img: 'img-1', url: 'https://example.test' },
      ],
      source_files: ['qa.csv'],
    });

    render(renderPane({ getTopicMergedCsv }, 0, ['隱藏題']));

    fireEvent.click(await screen.findByRole('button', { name: '下載' }));

    expect(downloadBlob).toHaveBeenCalledTimes(1);
    const [blob, filename] = vi.mocked(downloadBlob).mock.calls[0];
    await expect(blob.text()).resolves.toBe([
      '"index","q","a","img","url","display"',
      '"1","顯示題","顯示答","","","true"',
      '"2","隱藏題","隱藏答","img-1","https://example.test","false"',
    ].join('\n'));
    expect(filename).toBe('PRP.csv');
  });

  it('saves rows in their current order with a resequenced index', async () => {
    // Source rows arrive with non-sequential indices; the save path must
    // renumber them 1..N in display order. This is the persistence contract
    // that drag-reordering relies on (the reorder itself is exercised via the
    // table's keyboard grip in merged-csv-table.test, and end-to-end in the
    // browser — dnd-kit pointer/keyboard movement needs real layout geometry
    // that jsdom does not provide).
    const getTopicMergedCsv = vi.fn().mockResolvedValue({
      rows: [
        { index: '9', q: '第一題', a: 'A1', img: '', source_file: 'qa.csv' },
        { index: '4', q: '第二題', a: 'A2', img: '', source_file: 'qa.csv' },
        { index: '7', q: '第三題', a: 'A3', img: '', source_file: 'qa.csv' },
      ],
      source_files: ['qa.csv'],
    });
    const updateKnowledgeFileContent = vi.fn().mockResolvedValue(undefined);
    const updateTopic = vi.fn().mockResolvedValue(undefined);

    render(renderPane({
      getTopicMergedCsv,
      updateKnowledgeFileContent,
      updateTopic,
      deleteKnowledgeFile: vi.fn().mockResolvedValue(undefined),
    }, 0));

    fireEvent.click(await screen.findByRole('button', { name: '編輯題庫' }));
    fireEvent.click(screen.getByRole('button', { name: '儲存變更' }));

    await waitFor(() => expect(updateKnowledgeFileContent).toHaveBeenCalledTimes(1));
    expect(updateKnowledgeFileContent).toHaveBeenCalledWith(
      'qa.csv',
      [
        '"index","q","a","img","url"',
        '"1","第一題","A1","",""',
        '"2","第二題","A2","",""',
        '"3","第三題","A3","",""',
      ].join('\n'),
      'zh',
    );
    expect(updateTopic).toHaveBeenCalledWith('ortho/prp', { hidden_questions: [] }, 'zh');
  });
});
