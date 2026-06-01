import { afterEach, describe, it, expect, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import MergedCsvTable from '../../src/components/_shared/qaKnowledgeWorkspace/detail/MergedCsvTable';
import type { ComponentProps } from 'react';

type MergedCsvTableProps = ComponentProps<typeof MergedCsvTable>;

afterEach(() => {
  cleanup();
});

function createMergedCsvTableProps(props: Partial<MergedCsvTableProps> = {}): MergedCsvTableProps {
  return {
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
    onReorderRow: () => {},
    ...props,
  };
}

function renderMergedCsvTable(props: Partial<MergedCsvTableProps> = {}) {
  return render(<MergedCsvTable {...createMergedCsvTableProps(props)} />);
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

  it('does not link scheme-less URLs as relative app paths', () => {
    renderMergedCsvTable({
      rows: [
        { index: '001', q: 'Q1', a: 'A1', img: '', url: 'example.com/page' },
        { index: '002', q: 'Q2', a: 'A2', img: '', url: 'https://example.com/page' },
      ],
    });

    expect(screen.getByText('example.com/page').closest('a')).toBeNull();
    expect(screen.getByRole('link', { name: 'https://example.com/page' }).getAttribute('href')).toBe(
      'https://example.com/page',
    );
  });

  it('shows a keyboard-operable drag handle per row only while editing', () => {
    const props = {
      rows: [
        { index: '001', q: 'Q1', a: 'A1', img: '' },
        { index: '002', q: 'Q2', a: 'A2', img: '' },
      ],
    };

    const { rerender } = renderMergedCsvTable(props);
    // No grips in read-only mode.
    expect(screen.queryByRole('button', { name: /拖曳第/ })).toBeNull();

    rerender(<MergedCsvTable {...createMergedCsvTableProps({ ...props, isEditing: true })} />);

    const grips = screen.getAllByRole('button', { name: /拖曳第/ });
    expect(grips).toHaveLength(2);
    // dnd-kit makes the handle focusable + announces it as draggable.
    expect(grips[0].getAttribute('aria-roledescription')).toBe('sortable');
    expect(grips[0].tabIndex).toBe(0);
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
