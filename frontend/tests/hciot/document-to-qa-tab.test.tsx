import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import DocumentToQaTab from '../../src/components/_shared/qaKnowledgeWorkspace/upload/DocumentToQaTab';
import * as api from '../../src/services/api';

vi.mock('../../src/services/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../src/services/api')>()),
  createQaExtractJob: vi.fn(),
  getQaExtractJob: vi.fn(),
  importQaExtractJob: vi.fn(),
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
});
