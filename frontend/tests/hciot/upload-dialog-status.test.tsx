import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import UploadDialog from '../../src/components/hciot/knowledgeWorkspace/UploadDialog';
import React from 'react';

describe('UploadDialog', () => {
  it('detects duplicate files and adds warning', async () => {
    render(
      <UploadDialog 
        open={true}
        language="zh"
        categories={[]}
        uploading={false}
        onClose={() => {}}
        onUploadFile={async () => ({ name: 'test.csv' })}
        onUploadComplete={async () => {}}
        onSubmitQA={async () => {}}
      />
    );

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file1 = new File([''], 'test.csv', { type: 'text/csv' });
    
    // Add once
    fireEvent.change(input, { target: { files: [file1] } });
    
    // Add again (duplicate)
    fireEvent.change(input, { target: { files: [file1] } });
    
    const duplicateWarnings = await screen.findAllByText('(重複)');
    expect(duplicateWarnings.length).toBeGreaterThan(0);
  });
});