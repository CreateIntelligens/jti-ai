import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import MergedCsvTable from '../../src/components/hciot/knowledgeWorkspace/MergedCsvTable';
import * as api from '../../src/services/api/hciot';
import React from 'react';

vi.mock('../../src/services/api/hciot', async () => {
  const actual = await vi.importActual('../../src/services/api/hciot');
  return {
    ...actual,
    getHciotTopicMergedCsv: vi.fn(),
  };
});

describe('MergedCsvTable', () => {
  it('renders merged csv rows and thumbnails', async () => {
    vi.mocked(api.getHciotTopicMergedCsv).mockResolvedValue({
      rows: [
        { index: '001', q: 'Q1', a: 'A1', img: '' },
        { index: '002', q: 'Q2', a: 'A2', img: 'test_img.png' },
      ],
      source_files: ['file1.csv', 'file2.csv']
    });

    render(<MergedCsvTable topicId="test" language="zh" />);

    await waitFor(() => {
      expect(screen.getByText('Q1')).toBeInTheDocument();
      expect(screen.getByText('A1')).toBeInTheDocument();
      expect(screen.getByText('Q2')).toBeInTheDocument();
      expect(screen.getByText('A2')).toBeInTheDocument();
      expect(screen.getByText('已合併 2 個檔案')).toBeInTheDocument();
    });

    const img = screen.getByRole('img', { name: 'test_img.png' });
    expect(img).toHaveAttribute('src', '/api/hciot/images/test_img.png');
  });

  it('renders empty state', async () => {
    vi.mocked(api.getHciotTopicMergedCsv).mockResolvedValue({
      rows: [],
      source_files: []
    });

    render(<MergedCsvTable topicId="empty" language="zh" />);

    await waitFor(() => {
      expect(screen.getByText('此主題目前沒有 CSV 檔案。')).toBeInTheDocument();
    });
  });
});