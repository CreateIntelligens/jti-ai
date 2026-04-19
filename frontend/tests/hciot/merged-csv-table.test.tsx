import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import MergedCsvTable from '../../src/components/hciot/knowledgeWorkspace/detail/MergedCsvTable';
import React from 'react';

describe('MergedCsvTable', () => {
  it('renders merged csv rows and thumbnails', () => {
    render(
      <MergedCsvTable
        language="zh"
        rows={[
        { index: '001', q: 'Q1', a: 'A1', img: '' },
        { index: '002', q: 'Q2', a: 'A2', img: 'test_img.png' },
        ]}
        sourceFiles={['file1.csv', 'file2.csv']}
        availableImages={[]}
        loading={false}
        error={null}
        isEditing={false}
        onUpdateRow={() => {}}
        onDeleteRow={() => {}}
        onAddRow={() => {}}
      />,
    );

    expect(screen.getByText('Q1')).toBeTruthy();
    expect(screen.getByText('A1')).toBeTruthy();
    expect(screen.getByText('Q2')).toBeTruthy();
    expect(screen.getByText('A2')).toBeTruthy();
    expect(screen.getByText('已合併 2 個檔案')).toBeTruthy();

    const img = screen.getByRole('img', { name: 'test_img.png' });
    expect(img.getAttribute('src')).toBe('/api/hciot/images/test_img');
  });

  it('renders empty state', () => {
    render(
      <MergedCsvTable
        language="zh"
        rows={[]}
        sourceFiles={[]}
        availableImages={[]}
        loading={false}
        error={null}
        isEditing={false}
        onUpdateRow={() => {}}
        onDeleteRow={() => {}}
        onAddRow={() => {}}
      />,
    );

    expect(screen.getByText('此主題目前沒有 CSV 檔案。')).toBeTruthy();
  });
});
