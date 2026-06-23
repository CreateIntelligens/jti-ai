import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const SESSION_HINT_KEY = 'jtai:auth-session-known';

const apiMocks = vi.hoisted(() => ({
  getMe: vi.fn(),
  hasKnownAuthSession: vi.fn(() => window.localStorage.getItem(SESSION_HINT_KEY) === '1'),
  logout: vi.fn(),
}));

vi.mock('../src/services/api', () => apiMocks);

vi.mock('../src/pages/Login', () => ({
  default: () => <div data-testid="login-page">Login page</div>,
}));

vi.mock('../src/pages/Jti', () => ({
  default: () => <div>JTI page</div>,
}));

vi.mock('../src/pages/Hciot', () => ({
  default: () => <div>HCIoT page</div>,
}));

vi.mock('../src/pages/General', () => ({
  default: () => <div>General page</div>,
}));

vi.mock('../src/components/Header', () => ({
  default: () => <div>Header</div>,
}));

vi.mock('../src/components/Sidebar', () => ({
  default: () => <div>Sidebar</div>,
}));

vi.mock('../src/components/AdminPanel', () => ({
  default: () => <div>AdminPanel</div>,
}));

vi.mock('../src/components/ApiKeysPanel', () => ({
  default: () => <div>ApiKeysPanel</div>,
}));

vi.mock('../src/components/PromptPanel', () => ({
  default: () => <div>PromptPanel</div>,
}));

vi.mock('../src/components/ExtKeysPanel', () => ({
  default: () => <div>ExtKeysPanel</div>,
}));

vi.mock('../src/components/UsersPanel', () => ({
  default: () => <div>UsersPanel</div>,
}));

vi.mock('../src/components/ConversationHistoryModal', () => ({
  default: () => <div>ConversationHistoryModal</div>,
}));

vi.mock('../src/components/general/GeneralKnowledgeWorkspace', () => ({
  default: () => <div>GeneralKnowledgeWorkspace</div>,
}));

vi.mock('../src/components/hciot/HciotKnowledgeWorkspace', () => ({
  default: () => <div>HciotKnowledgeWorkspace</div>,
}));

vi.mock('../src/components/jti/JtiKnowledgeWorkspace', () => ({
  default: () => <div>JtiKnowledgeWorkspace</div>,
}));

vi.mock('../src/components/esg/EsgKnowledgeWorkspace', () => ({
  default: () => <div>EsgKnowledgeWorkspace</div>,
}));

vi.mock('../src/hooks/useAppChat', () => ({
  useAppChat: () => ({
    sidebarOpen: false,
    conversationHistoryModalOpen: false,
    setConversationHistoryModalOpen: vi.fn(),
    status: '',
    stores: [],
    filteredStores: [],
    keyNames: [],
    knowledgeTargets: [],
    currentTarget: null,
    currentTargetId: null,
    currentStore: null,
    messages: [],
    setMessages: vi.fn(),
    loading: false,
    initializing: false,
    sessionId: null,
    setSessionId: vi.fn(),
    managedContext: null,
    theme: 'light',
    toggleTheme: vi.fn(),
    toggleSidebar: vi.fn(),
    showStatus: vi.fn(),
    refreshStores: vi.fn(),
    handleRefreshKnowledge: vi.fn(),
    handleStoreChange: vi.fn(),
    handleRestartChat: vi.fn(),
    handleCreateStore: vi.fn(),
    handleDeleteStore: vi.fn(),
    handleSendMessage: vi.fn(),
    handleRegenerate: vi.fn(),
    handleEditAndResend: vi.fn(),
  }),
}));

import App from '../src/App';

describe('AuthGuard session hint', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    window.history.pushState({}, '', '/');
    apiMocks.getMe.mockRejectedValue(new Error('Missing session token or authorization credentials'));
    apiMocks.logout.mockResolvedValue({ ok: true });
  });

  it('redirects to login without probing /auth/me when no browser session hint exists', async () => {
    render(<App />);

    await screen.findByTestId('login-page');

    expect(apiMocks.getMe).not.toHaveBeenCalled();
  });

  it('probes /auth/me when a browser session hint exists', async () => {
    window.localStorage.setItem(SESSION_HINT_KEY, '1');
    apiMocks.getMe.mockResolvedValue({
      user_id: 'admin-1',
      username: 'alice',
      role: 'admin',
      scope: null,
      store_name: null,
    });

    render(<App />);

    await waitFor(() => expect(apiMocks.getMe).toHaveBeenCalled());
  });
});
