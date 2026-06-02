import { createRef } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import DocumentToQaSourceForm from '../src/components/_shared/qaKnowledgeWorkspace/upload/DocumentToQaSourceForm';

const CSV_EXAMPLE_HEADERS = ['index', 'q', 'a', 'img', 'url', 'display'] as const;

function renderFileMode() {
  return render(
    <DocumentToQaSourceForm
      language="zh"
      isEn={false}
      mode="file"
      fileItems={[]}
      text=""
      error={null}
      dragOver={false}
      fileInputRef={createRef<HTMLInputElement>()}
      canSubmit={false}
      onModeChange={vi.fn()}
      onTextChange={vi.fn()}
      onDragOverChange={vi.fn()}
      onFileSelect={vi.fn()}
      onRemoveFile={vi.fn()}
      onStartExtraction={vi.fn()}
      onClose={vi.fn()}
    />,
  );
}

describe('DocumentToQaSourceForm', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows a downloadable CSV format example in file mode', async () => {
    const createdBlobs: Blob[] = [];
    vi.spyOn(URL, 'createObjectURL').mockImplementation((blob) => {
      createdBlobs.push(blob as Blob);
      return 'blob:test-csv-example';
    });
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);

    renderFileMode();

    expect(screen.getByText('CSV 格式範例')).toBeTruthy();
    for (const header of CSV_EXAMPLE_HEADERS) {
      expect(screen.getByText(header)).toBeTruthy();
    }

    fireEvent.click(screen.getByRole('button', { name: '下載 CSV 範例' }));

    expect(createdBlobs).toHaveLength(1);
    await expect(createdBlobs[0].text()).resolves.toContain(CSV_EXAMPLE_HEADERS.join(','));
  });
});
