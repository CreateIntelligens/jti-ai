import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiMocks = vi.hoisted(() => ({
  fetchWithApiKey: vi.fn(),
  getHciotTtsCharacters: vi.fn(),
  hciotStartChat: vi.fn(),
  listHciotTopics: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('../../src/services/api', () => apiMocks);

vi.mock('../../src/components/hciot/HciotKnowledgeWorkspace', () => ({
  default: (props: any) => (
    <button type="button" onClick={() => props.onTopicsChanged?.()}>
      模擬題庫更新
    </button>
  ),
}));

import Hciot from '../../src/pages/Hciot';

describe('Hciot topic refresh', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    window.sessionStorage.clear();
    apiMocks.getHciotTtsCharacters.mockResolvedValue({ characters: [] });
    apiMocks.hciotStartChat.mockResolvedValue({ session_id: 'session-1', opening_message: '' });
  });

  it('reloads public quick questions after the knowledge workspace changes topics', async () => {
    apiMocks.listHciotTopics
      .mockResolvedValueOnce({
        categories: [
          { id: 'ortho', label: '骨科', topics: [{ id: 'ortho/prp', label: 'PRP', questions: ['舊問題'] }] },
        ],
      })
      .mockResolvedValueOnce({
        categories: [
          { id: 'ortho', label: '骨科', topics: [{ id: 'ortho/prp', label: 'PRP', questions: ['新問題'] }] },
        ],
      });

    render(<Hciot />);

    expect(await screen.findByText('舊問題')).toBeTruthy();

    await act(async () => {
      screen.getByRole('button', { name: '模擬題庫更新' }).click();
    });

    await waitFor(() => expect(apiMocks.listHciotTopics).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('新問題')).toBeTruthy();
  });
});
