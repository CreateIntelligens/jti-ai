import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import Header from '../src/components/Header';
import { fetchAppUpdateNotice, getAppUpdateNotice } from '../src/utils/appVersion';

const baseHeaderProps = {
  sidebarOpen: true,
  onToggleSidebar: vi.fn(),
  status: '',
  theme: 'light' as const,
  onToggleTheme: vi.fn(),
  canOpenConversationHistory: false,
  onOpenConversationHistory: vi.fn(),
  onOpenAdminPanel: vi.fn(),
  onOpenApiKeysPanel: vi.fn(),
  onOpenExtKeysPanel: vi.fn(),
  onShowStatus: vi.fn(),
};

describe('home update indicator', () => {
  it('reports an available update when the latest version is newer', () => {
    const notice = getAppUpdateNotice({
      VITE_APP_VERSION: '1.2.0',
      VITE_LATEST_APP_VERSION: '1.3.0',
    });

    expect(notice).toEqual({
      currentVersion: '1.2.0',
      latestVersion: '1.3.0',
    });
  });

  it('does not report an update when versions match', () => {
    const notice = getAppUpdateNotice({
      VITE_APP_VERSION: '1.2.0',
      VITE_LATEST_APP_VERSION: '1.2.0',
    });

    expect(notice).toBeNull();
  });

  it('shows a compact update alert in the home header', () => {
    render(
      <MemoryRouter>
        <div className="app-shell">
          <Header
            {...baseHeaderProps}
            updateNotice={{
              currentVersion: '1.2.0',
              latestVersion: '1.3.0',
            }}
          />
        </div>
      </MemoryRouter>,
    );

    expect(screen.getByRole('status', { name: '新版本可用：目前 1.2.0，最新 1.3.0' })).toBeTruthy();
  });

  it('fetches the latest version from the runtime manifest', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ version: '1.3.0' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const notice = await fetchAppUpdateNotice({
      appVersion: '1.2.0',
      env: { BASE_URL: '/' },
      fetcher,
    });

    expect(fetcher).toHaveBeenCalledWith('/version.json', { cache: 'no-store' });
    expect(notice).toEqual({
      currentVersion: '1.2.0',
      latestVersion: '1.3.0',
    });
  });

  it('stays quiet when the runtime manifest is unavailable', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('', { status: 404 }));

    const notice = await fetchAppUpdateNotice({
      appVersion: '1.2.0',
      env: { BASE_URL: '/' },
      fetcher,
    });

    expect(notice).toBeNull();
  });
});
