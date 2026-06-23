import React from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import QaKnowledgeWorkspace from '../src/components/_shared/qaKnowledgeWorkspace/QaKnowledgeWorkspace';
import EsgKnowledgeWorkspace from '../src/components/esg/EsgKnowledgeWorkspace';
import JtiKnowledgeWorkspace from '../src/components/jti/JtiKnowledgeWorkspace';

vi.mock('../src/components/_shared/qaKnowledgeWorkspace/QaKnowledgeWorkspace', () => ({
  default: vi.fn(() => <div data-testid="qa-workspace" />),
}));

describe('managed fixed-app knowledge workspaces', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('configures JTI as a standard QA workspace without image management', () => {
    render(<JtiKnowledgeWorkspace active language="zh" />);

    expect(vi.mocked(QaKnowledgeWorkspace).mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({
        active: true,
        language: 'zh',
        config: expect.objectContaining({
          sourceType: 'jti',
          disableAiQaExtraction: true,
          disableImages: true,
        }),
      }),
    );
  });

  it('configures ESG as a standard QA workspace without image management', () => {
    render(<EsgKnowledgeWorkspace active={false} language="en" />);

    expect(vi.mocked(QaKnowledgeWorkspace).mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({
        active: false,
        language: 'en',
        config: expect.objectContaining({
          sourceType: 'esg',
          disableAiQaExtraction: true,
          disableImages: true,
        }),
      }),
    );
  });
});
