import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

const apiMocks = vi.hoisted(() => ({
  fetchWithApiKey: vi.fn(),
  getHciotTtsCharacters: vi.fn(),
  hciotStartChat: vi.fn(),
  listHciotTopics: vi.fn(),
  getMe: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('../../src/services/api', () => apiMocks);

vi.mock('../../src/components/hciot/HciotKnowledgeWorkspace', () => ({
  default: () => <div>Mock Workspace</div>,
}));

import Hciot from '../../src/pages/Hciot';

describe('Hciot topic selection persistence', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    window.sessionStorage.clear();
    apiMocks.getMe.mockResolvedValue({
      user_id: 'user-1',
      username: 'testuser',
      role: 'user',
      app: 'hciot',
      store_name: null,
    });
    apiMocks.getHciotTtsCharacters.mockResolvedValue({ characters: [] });
    apiMocks.hciotStartChat.mockResolvedValue({ session_id: 'session-1', opening_message: '' });
  });

  it('restores category and topic from localStorage on load', async () => {
    window.localStorage.setItem('hciot:selected-category', 'ortho');
    window.localStorage.setItem('hciot:selected-topic', 'ortho/prp');

    apiMocks.listHciotTopics.mockResolvedValue({
      categories: [
        {
          id: '常见問題',
          label: '常見問題',
          topics: [{ id: '常见問題/門診', label: '門診', questions: ['門診問題'] }],
        },
        {
          id: 'ortho',
          label: '骨科',
          topics: [{ id: 'ortho/prp', label: 'PRP', questions: ['骨科問題'] }],
        },
      ],
    });

    render(
      <MemoryRouter>
        <Hciot />
      </MemoryRouter>
    );

    // Should display the restored topic's questions (骨科問題) instead of the default first category (門診問題)
    expect(await screen.findByText('骨科問題')).toBeTruthy();
  });
});
