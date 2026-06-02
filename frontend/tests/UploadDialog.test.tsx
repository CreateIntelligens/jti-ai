import { fireEvent, render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import UploadDialog from '../src/components/_shared/qaKnowledgeWorkspace/upload/UploadDialog';

vi.mock('../src/components/_shared/qaKnowledgeWorkspace/upload/DocumentToQaTab', () => ({
  default: () => <div data-testid="document-tab" />,
}));

vi.mock('../src/components/_shared/qaKnowledgeWorkspace/upload/ImageUploadTab', () => ({
  default: () => <div data-testid="image-tab" />,
}));

vi.mock('../src/components/_shared/qaKnowledgeWorkspace/upload/QaUploadTab', () => ({
  default: () => <div data-testid="qa-tab" />,
}));

vi.mock('../src/components/_shared/qaKnowledgeWorkspace/upload/UploadTopicSelector', () => ({
  default: () => <div data-testid="topic-selector" />,
}));

function renderUploadDialog(onClose = vi.fn()) {
  const result = render(
    <UploadDialog
      open
      language="zh"
      categories={[]}
      availableImages={[]}
      uploading={false}
      onClose={onClose}
      onUploadFile={vi.fn()}
      onUploadComplete={vi.fn()}
      onSubmitQA={vi.fn()}
      api={{} as never}
      onUploadImage={vi.fn()}
      onUploadImageComplete={vi.fn()}
    />,
  );

  return { ...result, onClose };
}

function getElement(container: HTMLElement, selector: string) {
  const element = container.querySelector(selector);
  expect(element).not.toBeNull();
  return element as HTMLElement;
}

describe('UploadDialog', () => {
  it('does not close when a press starts inside the dialog and ends on the overlay', () => {
    const { container, onClose } = renderUploadDialog();
    const overlay = getElement(container, '.qa-workspace-qa-overlay');
    const dialog = getElement(container, '.qa-workspace-qa-dialog');

    fireEvent.mouseDown(dialog);
    fireEvent.mouseUp(overlay);
    fireEvent.click(overlay);

    expect(onClose).not.toHaveBeenCalled();
  });

  it('closes when a press starts and ends on the overlay', () => {
    const { container, onClose } = renderUploadDialog();
    const overlay = getElement(container, '.qa-workspace-qa-overlay');

    fireEvent.mouseDown(overlay);
    fireEvent.mouseUp(overlay);

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
