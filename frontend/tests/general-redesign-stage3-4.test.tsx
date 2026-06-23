import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Header from '../src/components/Header';
import Sidebar from '../src/components/Sidebar';

const baseHeaderProps = {
  sidebarOpen: true,
  onToggleSidebar: vi.fn(),
  status: '',
  theme: 'light' as const,
  onToggleTheme: vi.fn(),
  canOpenConversationHistory: true,
  onOpenConversationHistory: vi.fn(),
  onOpenAdminPanel: vi.fn(),
  onOpenApiKeysPanel: vi.fn(),
  onOpenExtKeysPanel: vi.fn(),
  onOpenPromptPanel: vi.fn(),
  onRefresh: vi.fn(),
  onShowStatus: vi.fn(),
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('General redesign stages 3 and 4', () => {
  it('groups the header settings menu around the five primary design actions', () => {
    render(
      <MemoryRouter>
        <div className="app-shell">
          <Header
            {...baseHeaderProps}
            userProfile={{ role: 'super_admin', username: 'root', user_id: 'root', scope: 'general', store_name: null }}
            onOpenUsersPanel={vi.fn()}
            onLogout={vi.fn()}
            canShow={() => false}
          />
        </div>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTitle('設定'));

    const menu = screen.getByRole('menu');
    const buttonLabels = within(menu).getAllByRole('button').map((button) => button.textContent?.trim());

    expect(buttonLabels).toEqual([
      '知識庫管理',
      'API Key 設定',
      '對外 API Keys',
      'Prompt 設定',
      '重新索引 RAG',
      '帳號管理',
      '全域同步至備援庫',
      '從備援庫補回主庫',
      '登出',
    ]);
  });

  it('opens the create-store flow as a centered modal from the sidebar', () => {
    const onCreateStore = vi.fn().mockResolvedValue(undefined);

    render(
      <Sidebar
        isOpen
        stores={[]}
        keyNames={['專案 A', '專案 B']}
        knowledgeTargets={[]}
        currentTargetId={null}
        onTargetChange={vi.fn()}
        onCreateStore={onCreateStore}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /新增知識庫/ }));

    expect(screen.getByRole('dialog', { name: '建立知識庫' })).toBeTruthy();
    expect(screen.queryByPlaceholderText('知識庫名稱...')).toBeNull();
  });
});
