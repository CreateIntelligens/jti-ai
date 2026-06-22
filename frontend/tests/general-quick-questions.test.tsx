import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiMocks = vi.hoisted(() => ({
  listGeneralTopics: vi.fn(),
}));

vi.mock('../src/services/api/general', () => apiMocks);

import General from '../src/pages/General';

describe('General quick questions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.listGeneralTopics.mockResolvedValue({
      categories: [
        {
          id: 'visible-category',
          label: '可見分類',
          topics: [
            {
              id: 'visible-topic',
              label: '可見主題',
              questions: ['顯示問題', '隱藏問題'],
              hidden_questions: ['隱藏問題'],
            },
            {
              id: 'hidden-topic',
              label: '隱藏主題',
              questions: ['不應顯示'],
              hidden: true,
            },
          ],
        },
        {
          id: 'hidden-category',
          label: '隱藏分類',
          hidden: true,
          topics: [
            { id: 'hidden-category-topic', label: '不應顯示分類', questions: ['不應顯示分類問題'] },
          ],
        },
      ],
    });
  });

  it('loads visible topics for the selected store and sends chip text through general chat', async () => {
    const onSendMessage = vi.fn();

    render(
      <General
        storeName="store-a"
        messages={[]}
        onSendMessage={onSendMessage}
        disabled={false}
        loading={false}
        currentStoreName="Store A"
      />,
    );

    await waitFor(() => expect(apiMocks.listGeneralTopics).toHaveBeenCalledWith('store-a'));
    expect(await screen.findByText('顯示問題')).toBeTruthy();
    expect(screen.queryByText('隱藏問題')).toBeNull();
    expect(screen.queryByText('不應顯示')).toBeNull();
    expect(screen.queryByText('隱藏分類')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /顯示問題/ }));

    expect(onSendMessage).toHaveBeenCalledWith('顯示問題');
  });
});
