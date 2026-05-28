import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import UploadDialog from '../../src/components/_shared/qaKnowledgeWorkspace/upload/UploadDialog';

describe('UploadDialog', () => {
  it('keeps one selected knowledge file in the unified upload tab', async () => {
    render(
      <UploadDialog 
        open={true}
        language="zh"
        categories={[]}
        availableImages={[]}
        uploading={false}
        onClose={() => {}}
        onUploadFile={async () => ({ name: 'test.csv' })}
        onUploadComplete={async () => {}}
        onSubmitQA={async () => {}}
        onUploadImage={async () => ({ image_id: 'img-1', url: '/api/hciot/images/img-1' })}
        onUploadImageComplete={async () => {}}
      />
    );

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const firstFile = new File([''], 'first.csv', { type: 'text/csv' });
    const secondFile = new File([''], 'second.csv', { type: 'text/csv' });
    
    fireEvent.change(input, { target: { files: [firstFile] } });
    expect(await screen.findByText('first.csv')).toBeTruthy();

    fireEvent.change(input, { target: { files: [secondFile] } });

    expect(await screen.findByText('second.csv')).toBeTruthy();
    expect(screen.queryByText('first.csv')).toBeNull();
  });
});
