import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import QaKnowledgeWorkspace, {
  type QaWorkspaceConfig,
} from '../../src/components/_shared/qaKnowledgeWorkspace/QaKnowledgeWorkspace';

function createApi(overrides: Record<string, unknown> = {}) {
  return {
    listKnowledgeFiles: vi.fn().mockResolvedValue({ files: [] }),
    listTopicsAdmin: vi.fn().mockResolvedValue({
      categories: [
        {
          id: 'ortho',
          label: '骨科',
          order: 1,
          hidden: false,
          topics: [
            {
              id: 'ortho/prp',
              label: 'PRP',
              order: 1,
              questions: ['Q1'],
              hidden_questions: [],
              hidden: false,
            },
            {
              id: 'ortho/faq',
              label: '常見問題',
              order: 2,
              questions: ['Q2'],
              hidden_questions: [],
              hidden: true,
            },
          ],
        },
      ],
    }),
    listImages: vi.fn().mockResolvedValue({ images: [] }),
    getReindexStatus: vi.fn().mockResolvedValue({ reindexing: false }),
    reindex: vi.fn().mockResolvedValue({}),
    getKnowledgeFileContent: vi.fn(),
    uploadKnowledgeFileWithTopic: vi.fn(),
    deleteKnowledgeFile: vi.fn(),
    updateTopic: vi.fn().mockResolvedValue({}),
    reorderTopics: vi.fn().mockResolvedValue({ updated: 2 }),
    setCategoryHidden: vi.fn().mockResolvedValue({ category_id: 'ortho', hidden: true }),
    uploadImage: vi.fn(),
    deleteImage: vi.fn(),
    deleteUnusedImages: vi.fn(),
    createTopic: vi.fn(),
    updateKnowledgeFileMetadata: vi.fn(),
    updateKnowledgeFileContent: vi.fn(),
    downloadKnowledgeFile: vi.fn(),
    getTopicMergedCsv: vi.fn(),
    createQaExtractJob: vi.fn(),
    parseQaCsvText: vi.fn(),
    getQaExtractJob: vi.fn(),
    importQaExtractJob: vi.fn(),
    ...overrides,
  };
}

function renderWorkspace(api = createApi()) {
  const config: QaWorkspaceConfig = {
    sourceType: 'hciot',
    api: api as any,
    text: (_language, zh) => zh,
  };

  render(
    <QaKnowledgeWorkspace
      active
      language="zh"
      config={config}
    />,
  );

  return api;
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  window.localStorage.clear();
});

describe('VisibilityOrderModal', () => {
  it('saves category and topic visibility changes from the workspace management modal', async () => {
    const api = renderWorkspace();

    fireEvent.click(await screen.findByRole('button', { name: '管理科別與主題' }));

    const categoryCheckbox = screen.getByRole('checkbox', { name: '顯示科別：骨科' }) as HTMLInputElement;
    const visibleTopicCheckbox = screen.getByRole('checkbox', { name: '顯示主題：PRP' }) as HTMLInputElement;
    const hiddenTopicCheckbox = screen.getByRole('checkbox', { name: '顯示主題：常見問題' }) as HTMLInputElement;

    expect(categoryCheckbox.checked).toBe(true);
    expect(visibleTopicCheckbox.checked).toBe(true);
    expect(hiddenTopicCheckbox.checked).toBe(false);

    fireEvent.click(categoryCheckbox);
    fireEvent.click(visibleTopicCheckbox);
    fireEvent.click(screen.getByRole('button', { name: '儲存管理設定' }));

    await waitFor(() => expect(api.setCategoryHidden).toHaveBeenCalledWith('ortho', true, 'zh'));
    expect(api.updateTopic).toHaveBeenCalledWith('ortho/prp', { hidden: true }, 'zh');
    expect(api.reorderTopics).toHaveBeenCalledWith(['ortho/prp', 'ortho/faq'], 'zh');
  });
});
