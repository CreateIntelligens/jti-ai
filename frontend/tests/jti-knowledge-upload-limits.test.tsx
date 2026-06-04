import { fireEvent, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import JtiKnowledgeTab from '../src/components/jti/JtiKnowledgeTab';
import { MAX_UPLOAD_FILE_SIZE_BYTES, UPLOAD_FILE_SIZE_ERROR } from '../src/utils/uploadLimits';

function renderKnowledgeTab(onUploadFiles = vi.fn()) {
  const result = render(
    <JtiKnowledgeTab
      language="zh"
      kbFiles={[]}
      kbLoading={false}
      uploading={false}
      successMsg={null}
      onUploadFiles={onUploadFiles}
      onViewFile={vi.fn()}
      onDownloadFile={vi.fn()}
      onDeleteFileClick={vi.fn()}
      confirmDeleteFile={null}
      deletingFiles={[]}
      onDeleteFileConfirm={vi.fn()}
      onDeleteFileCancel={vi.fn()}
      viewingFile={null}
      fileContent=""
      fileEditable={false}
      fileLoading={false}
      isEditing={false}
      fileEditContent=""
      saving={false}
      onStartEdit={vi.fn()}
      onCancelEdit={vi.fn()}
      onSaveEdit={vi.fn()}
      onFileEditContentChange={vi.fn()}
      onCloseViewer={vi.fn()}
    />,
  );

  return { ...result, onUploadFiles };
}

describe('JtiKnowledgeTab upload limits', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('alerts and skips upload callback when a selected file is over the shared limit', () => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => undefined);
    const { container, onUploadFiles } = renderKnowledgeTab();
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const largeFile = new File(
      [new Uint8Array(MAX_UPLOAD_FILE_SIZE_BYTES + 1)],
      'large.txt',
      { type: 'text/plain' },
    );

    fireEvent.change(input, { target: { files: [largeFile] } });

    expect(alertSpy).toHaveBeenCalledWith(UPLOAD_FILE_SIZE_ERROR);
    expect(onUploadFiles).not.toHaveBeenCalled();
  });
});
