import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
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

describe('Hciot management menu', () => {
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
    apiMocks.listHciotTopics.mockResolvedValue({ categories: [] });
  });

  it('links to the bundled operation manual from the management menu', async () => {
    render(
      <MemoryRouter>
        <Hciot />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('button', { name: '管理' }));

    const manualLink = screen.getByRole('link', { name: /操作手冊/ });
    expect(manualLink.getAttribute('href')).toBe('/hciot-manual.html');
    expect(manualLink.getAttribute('target')).toBe('_blank');
  });
});
