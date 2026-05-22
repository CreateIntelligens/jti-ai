import { afterEach, describe, it, expect, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import MergedCsvTable from '../../src/components/hciot/knowledgeWorkspace/detail/MergedCsvTable';
import React from 'react';

type MergedCsvTableProps = React.ComponentProps<typeof MergedCsvTable>;

afterEach(() => {
  cleanup();
});

function renderMergedCsvTable(props: Partial<MergedCsvTableProps> = {}) {
  const defaultProps: MergedCsvTableProps = {
    language: 'zh',
    rows: [],
    sourceFiles: ['file1.csv'],
    availableImages: [],
    loading: false,
    error: null,
    isEditing: false,
    hiddenQuestions: new Set(),
    onUpdateRow: () => {},
    onDeleteRow: () => {},
    onAddRow: () => {},
    onToggleVisible: () => {},
  };

  return render(<MergedCsvTable {...defaultProps} {...props} />);
}

describe('MergedCsvTable', () => {
  it('renders merged csv rows and thumbnails', () => {
    renderMergedCsvTable({
      rows: [
        { index: '001', q: 'Q1', a: 'A1', img: '' },
        { index: '002', q: 'Q2', a: 'A2', img: 'test_img.png' },
      ],
      sourceFiles: ['file1.csv', 'file2.csv'],
    });

    expect(screen.getByText('Q1')).toBeTruthy();
    expect(screen.getByText('A1')).toBeTruthy();
    expect(screen.getByText('Q2')).toBeTruthy();
    expect(screen.getByText('A2')).toBeTruthy();
    expect(screen.getByText('已合併 2 個檔案')).toBeTruthy();

    const img = screen.getByRole('img', { name: 'test_img.png' });
    expect(img.getAttribute('src')).toBe('/api/hciot/images/test_img');
  });

  it('renders empty state', () => {
    renderMergedCsvTable({ sourceFiles: [] });

    expect(screen.getByText('此主題目前沒有 CSV 檔案。')).toBeTruthy();
  });

  it('shows readonly visibility states before entering edit mode', () => {
    renderMergedCsvTable({
      rows: [
        { index: '001', q: 'Q1', a: 'A1', img: '' },
        { index: '002', q: 'Q2', a: 'A2', img: '' },
      ],
      hiddenQuestions: new Set(['Q2']),
    });

    const visibleCheckbox = screen.getByRole('checkbox', { name: '顯示問題：Q1' }) as HTMLInputElement;
    const hiddenCheckbox = screen.getByRole('checkbox', { name: '顯示問題：Q2' }) as HTMLInputElement;

    expect(screen.getByRole('columnheader', { name: '顯示' })).toBeTruthy();
    expect(visibleCheckbox.checked).toBe(true);
    expect(hiddenCheckbox.checked).toBe(false);
    expect(visibleCheckbox.readOnly).toBe(true);
    expect(hiddenCheckbox.readOnly).toBe(true);
  });

  it('toggles all question visibility from the header checkbox', () => {
    const onToggleVisible = vi.fn();

    renderMergedCsvTable({
      rows: [
        { index: '001', q: 'Q1', a: 'A1', img: '' },
        { index: '002', q: 'Q2', a: 'A2', img: '' },
        { index: '003', q: '   ', a: 'A3', img: '' },
      ],
      isEditing: true,
      hiddenQuestions: new Set(['Q2']),
      onToggleVisible,
    });

    const selectAll = screen.getByRole('checkbox', { name: '全選顯示問題' }) as HTMLInputElement;
    expect(selectAll.checked).toBe(false);
    expect(selectAll.indeterminate).toBe(true);

    fireEvent.click(selectAll);

    expect(onToggleVisible).toHaveBeenCalledTimes(2);
    expect(onToggleVisible).toHaveBeenNthCalledWith(1, 'Q1', true);
    expect(onToggleVisible).toHaveBeenNthCalledWith(2, 'Q2', true);
  });
});
