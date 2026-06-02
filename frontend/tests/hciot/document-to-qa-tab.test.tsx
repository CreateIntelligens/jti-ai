import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import DocumentToQaTab from '../../src/components/_shared/qaKnowledgeWorkspace/upload/DocumentToQaTab';
import * as api from '../../src/services/api';

vi.mock('../../src/services/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../src/services/api')>()),
  createQaExtractJob: vi.fn(),
  getQaExtractJob: vi.fn(),
  importQaExtractJob: vi.fn(),
  parseQaCsvText: vi.fn(),
}));

describe('DocumentToQaTab', () => {
  const resolvedTopic = {
    fullTopicId: 'cat-1/topic-1',
    labels: {
      categoryLabel: 'Cat 1',
      topicLabel: 'Topic 1',
    },
  };

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('routes TXT files directly to the AI extraction endpoint', async () => {
    vi.mocked(api.createQaExtractJob).mockResolvedValue({
      job_id: 'job-1',
      status: 'pending',
    });

    const onUploadFile = vi.fn().mockResolvedValue({ name: 'direct.csv' });

    render(
      <DocumentToQaTab
        open
        language="zh"
        uploading={false}
        resolvedTopic={resolvedTopic}
        topicSelectionIncomplete={false}
        onClose={() => {}}
        onUploadFile={onUploadFile}
        onUploadComplete={async () => {}}
        api={api}
      />,
    );

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['hello'], 'notes.txt', { type: 'text/plain' });

    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: /開始 AI 擷取/ }));

    await waitFor(() => {
      expect(api.createQaExtractJob).toHaveBeenCalledWith(
        'zh',
        { file },
        'cat-1',
        'cat-1/topic-1',
        'Cat 1',
        'Topic 1',
      );
    });
    expect(onUploadFile).not.toHaveBeenCalled();
  });

  it('opens CSV files with display values in preview before importing', async () => {
    const onUploadFile = vi.fn().mockResolvedValue({ name: 'questions.csv' });
    const csvText = [
      'index,q,a,img,url,display',
      '1,顯示題,顯示答,,https://example.test,true',
      '2,隱藏題,隱藏答,,,false',
    ].join('\n');
    const expectedUploadedCsv = [
      'index,q,a,img,url',
      ',顯示題,顯示答,,https://example.test',
      ',隱藏題,隱藏答,,',
    ].join('\n');

    vi.mocked(api.parseQaCsvText).mockResolvedValue({
      parsed: true,
      qa_pairs: [
        { q: '顯示題', a: '顯示答', img: '', url: 'https://example.test', display: 'true' },
        { q: '隱藏題', a: '隱藏答', img: '', url: '', display: 'false' },
      ],
    });

    render(
      <DocumentToQaTab
        open
        language="zh"
        uploading={false}
        resolvedTopic={resolvedTopic}
        topicSelectionIncomplete={false}
        onClose={() => {}}
        onUploadFile={onUploadFile}
        onUploadComplete={async () => {}}
        api={api}
      />,
    );

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File([csvText], 'questions.csv', { type: 'text/csv' });

    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: /開始上傳/ }));

    expect(await screen.findByText('擷取到 2 組問答對')).toBeTruthy();
    expect(onUploadFile).not.toHaveBeenCalled();

    const visibilityCheckboxes = Array.from(
      document.querySelectorAll<HTMLInputElement>('.qa-workspace-qa-row-visible-checkbox'),
    );
    expect(visibilityCheckboxes).toHaveLength(2);
    expect(visibilityCheckboxes[0].checked).toBe(true);
    expect(visibilityCheckboxes[1].checked).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: '確認匯入' }));

    await waitFor(() => expect(onUploadFile).toHaveBeenCalledTimes(1));
    const [uploadedFile, topicId, labels, hiddenQuestions] = onUploadFile.mock.calls[0];
    expect(topicId).toBe('cat-1/topic-1');
    expect(labels).toEqual(resolvedTopic.labels);
    expect(hiddenQuestions).toEqual(['隱藏題']);
    await expect((uploadedFile as File).text()).resolves.toBe(expectedUploadedCsv);
  });
});
