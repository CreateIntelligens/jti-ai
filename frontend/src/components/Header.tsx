import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  CircleAlert,
  Database,
  DatabaseBackup,
  DatabaseZap,
  House,
  History,
  KeyRound,
  Link2,
  Loader2,
  Menu,
  Moon,
  PanelLeftClose,
  RefreshCw,
  Settings,
  Sun,
  Users,
  LogOut,
} from 'lucide-react';

import reindexRag from '../services/api/general';
import * as api from '../services/api';
import { useLogoutRedirect } from '../hooks/useLogoutRedirect';
import { isAdminRole, isSuperAdmin } from '../utils/authRouting';
import { fetchAppUpdateNotice, getAppUpdateNotice, type AppUpdateNotice } from '../utils/appVersion';

interface HeaderProps {
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  status: string;
  theme: 'dark' | 'light';
  onToggleTheme: () => void;
  canOpenConversationHistory: boolean;
  onOpenConversationHistory: () => void;
  onOpenAdminPanel: () => void;
  onOpenApiKeysPanel: () => void;
  onOpenExtKeysPanel: () => void;
  onOpenPromptPanel?: () => void;
  onRefresh?: () => void | Promise<void>;
  onShowStatus: (msg: string) => void;
  userProfile?: api.UserProfile | null;
  onOpenUsersPanel?: () => void;
  onLogout?: () => void;
  updateNotice?: AppUpdateNotice | null;
  canShow?: (page: string) => boolean;
}

const APP_NAV_OPTIONS = [
  { page: 'home', value: '/', label: 'ai360 km 通用知識庫' },
  { page: 'hciot', value: '/hciot', label: 'HCIoT 衛教助手' },
  { page: 'jti', value: '/jti', label: 'JTI 智慧助手' },
];

export function buildAppNavOptions(canShow?: (page: string) => boolean) {
  return APP_NAV_OPTIONS
    .filter((option) => !canShow || canShow(option.page))
    .map(({ value, label }) => ({ value, label }));
}

export default function Header({
  sidebarOpen,
  onToggleSidebar,
  status,
  theme,
  onToggleTheme,
  canOpenConversationHistory,
  onOpenConversationHistory,
  onOpenAdminPanel,
  onOpenApiKeysPanel,
  onOpenExtKeysPanel,
  onOpenPromptPanel,
  onRefresh,
  onShowStatus,
  userProfile,
  onOpenUsersPanel,
  onLogout,
  updateNotice,
  canShow,
}: HeaderProps) {
  const navigate = useNavigate();
  const isUpdateNoticeControlled = updateNotice !== undefined;
  const [runtimeUpdateNotice, setRuntimeUpdateNotice] = useState<AppUpdateNotice | null>(() => (
    isUpdateNoticeControlled ? null : getAppUpdateNotice()
  ));
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [isReindexing, setIsReindexing] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  const isAdmin = isAdminRole(userProfile?.role);
  const isSuper = isSuperAdmin(userProfile?.role);
  const handleLogoutClick = useLogoutRedirect(onLogout);
  const visibleUpdateNotice = isUpdateNoticeControlled ? updateNotice : runtimeUpdateNotice;
  const updateNoticeLabel = visibleUpdateNotice
    ? `新版本可用：目前 ${visibleUpdateNotice.currentVersion}，最新 ${visibleUpdateNotice.latestVersion}`
    : '';

  useEffect(() => {
    if (isUpdateNoticeControlled) return undefined;

    let active = true;
    void fetchAppUpdateNotice().then((notice) => {
      if (active) setRuntimeUpdateNotice(notice);
    });

    return () => {
      active = false;
    };
  }, [isUpdateNoticeControlled]);

  // Close the settings menu on an outside click or Escape. Listening on the
  // document (not just the header) means clicks anywhere on the page dismiss it.
  useEffect(() => {
    if (!settingsOpen) return undefined;

    const handlePointerDown = (event: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) {
        setSettingsOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setSettingsOpen(false);
    };

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [settingsOpen]);

  const openPanel = (openFn: () => void) => {
    openFn();
    setSettingsOpen(false);
  };

  const handleRefresh = async () => {
    if (!onRefresh || isRefreshing) return;
    setIsRefreshing(true);
    try {
      await onRefresh();
      onShowStatus('✅ 知識庫已重新整理');
    } catch (error) {
      onShowStatus(error instanceof Error ? error.message : '重新整理失敗');
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleReindexRag = async () => {
    if (isReindexing) return;
    setSettingsOpen(false);
    const confirmed = window.confirm(
      '重建知識庫索引會重新整理 embedding，期間服務可能暫停約 1 分鐘。是否繼續？',
    );
    if (!confirmed) return;
    setIsReindexing(true);
    onShowStatus('重新索引已啟動...');
    try {
      await reindexRag('all');
      onShowStatus('✅ 重新索引完成');
    } catch (error) {
      onShowStatus(error instanceof Error ? error.message : '重新索引失敗');
    } finally {
      setIsReindexing(false);
    }
  };

  const handleGlobalDbSync = async () => {
    if (isSyncing) return;
    setSettingsOpen(false);
    const confirmed = window.confirm(
      '全域同步會將所有應用資料與系統設定同步至備援庫，可能需要約 1 分鐘。是否繼續？',
    );
    if (!confirmed) return;
    setIsSyncing(true);
    onShowStatus('全域同步已啟動...');
    try {
      const result = await api.triggerDbSync('general');
      const dbCount = Object.keys(result.databases).length;
      onShowStatus(
        `✅ 全域同步完成（${dbCount} 庫）：新增 ${result.total_upserted}、` +
          `實際更新 ${result.total_modified}，耗時 ${result.elapsed_sec}s`,
      );
    } catch (error) {
      onShowStatus(error instanceof Error ? error.message : '全域同步失敗');
    } finally {
      setIsSyncing(false);
    }
  };

  const handleReverseRestore = async () => {
    if (isSyncing) return;
    setSettingsOpen(false);
    // 反向會寫「主庫」,危險。先 dry-run 預演,顯示會補幾筆,使用者確認後才正式寫。
    setIsSyncing(true);
    onShowStatus('預演中:計算需補回主庫的資料...');
    try {
      const preview = await api.triggerDbSync('general', { direction: 'reverse', dryRun: true });
      if (preview.total_inserted === 0) {
        onShowStatus('✅ 主庫已是最新,沒有需要補回的資料');
        return;
      }
      const confirmed = window.confirm(
        `預演結果:備援庫有 ${preview.total_inserted} 筆主庫沒有的資料。\n\n` +
          '這會把這些資料補回主庫(DocumentDB)。衝突時以主庫(AWS)為準,只補不覆蓋既有資料。\n\n' +
          '確定要補回主庫嗎？',
      );
      if (!confirmed) {
        onShowStatus('已取消反向補資料');
        return;
      }
      onShowStatus('補回主庫中...');
      const result = await api.triggerDbSync('general', { direction: 'reverse' });
      onShowStatus(
        `✅ 反向補資料完成:補入 ${result.total_inserted} 筆、` +
          `略過(主庫已有)${result.total_skipped} 筆,耗時 ${result.elapsed_sec}s`,
      );
    } catch (error) {
      onShowStatus(error instanceof Error ? error.message : '反向補資料失敗');
    } finally {
      setIsSyncing(false);
    }
  };

  return (
    <header className="app-header">
      <div className="header-left">
        <button
          className="sidebar-toggle"
          onClick={onToggleSidebar}
          aria-label={sidebarOpen ? '關閉側邊欄' : '開啟側邊欄'}
        >
          {sidebarOpen ? <PanelLeftClose size={18} /> : <Menu size={18} />}
        </button>
        <div className="app-logo">
          AI360 <span>Knowledge</span>
        </div>
        {visibleUpdateNotice && (
          <span
            className="version-update-indicator"
            role="status"
            aria-label={updateNoticeLabel}
            title={updateNoticeLabel}
          >
            <CircleAlert />
          </span>
        )}
        {status && <div className="status-badge">{status}</div>}
      </div>

      <div className="header-right">
        <button
          className="icon-btn"
          title="對話歷史"
          disabled={!canOpenConversationHistory}
          onClick={onOpenConversationHistory}
        >
          <History size={18} />
        </button>
        <button
          className={`icon-btn${isRefreshing ? ' is-spinning' : ''}`}
          onClick={() => void handleRefresh()}
          title="重新整理知識庫"
          disabled={!onRefresh || isRefreshing}
        >
          <RefreshCw size={18} />
        </button>
        <button
          className="icon-btn"
          onClick={onToggleTheme}
          title={theme === 'dark' ? '切換為淺色主題' : '切換為深色主題'}
        >
          {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
        </button>
        <div className="dd-wrap" ref={wrapRef}>
          <button
            className="icon-btn"
            onClick={() => setSettingsOpen((open) => !open)}
            title="設定"
            aria-expanded={settingsOpen}
            aria-haspopup="menu"
          >
            <Settings size={18} />
          </button>
          {settingsOpen && (
            <div className="dd-menu" role="menu">
              <div className="dd-section-label">面板</div>
              {isAdmin && (
                <button className="dd-item" onClick={() => openPanel(onOpenAdminPanel)}>
                  <Database size={16} /> 知識庫管理
                </button>
              )}
              <button className="dd-item" onClick={() => openPanel(onOpenApiKeysPanel)}>
                <KeyRound size={16} /> API Key 設定
              </button>
              <button className="dd-item" onClick={() => openPanel(onOpenExtKeysPanel)}>
                <Link2 size={16} /> 對外 API Keys
              </button>
              {onOpenPromptPanel && (
                <button className="dd-item" onClick={() => openPanel(onOpenPromptPanel)}>
                  <Settings size={16} /> Prompt 設定
                </button>
              )}
              {isAdmin && (
                <>
                  <div className="dd-sep" />
                  <button className="dd-item" onClick={handleReindexRag} disabled={isReindexing}>
                    {isReindexing ? <Loader2 size={16} /> : <RefreshCw size={16} />}
                    重新索引 RAG
                  </button>
                  <div className="dd-sep" />
                  <div className="dd-section-label">進階</div>
                  {onOpenUsersPanel && (
                    <button className="dd-item" onClick={() => openPanel(onOpenUsersPanel)}>
                      <Users size={16} /> 帳號管理
                    </button>
                  )}
                  {isSuper && (
                    <>
                      <button className="dd-item" onClick={handleGlobalDbSync} disabled={isSyncing}>
                        {isSyncing ? <Loader2 size={16} /> : <DatabaseBackup size={16} />}
                        全域同步至備援庫
                      </button>
                      <button className="dd-item" onClick={handleReverseRestore} disabled={isSyncing}>
                        {isSyncing ? <Loader2 size={16} /> : <DatabaseZap size={16} />}
                        從備援庫補回主庫
                      </button>
                    </>
                  )}
                </>
              )}

              {isAdmin && buildAppNavOptions(canShow).length > 1 && (
                <>
                  <div className="dd-sep" />
                  <div className="dd-section-label">切換應用</div>
                  {buildAppNavOptions(canShow).map((option) => (
                    <button
                      key={option.value}
                      className="dd-item"
                      onClick={() => {
                        navigate(option.value);
                        setSettingsOpen(false);
                      }}
                    >
                      <House size={16} /> {option.label}
                    </button>
                  ))}
                </>
              )}

              {userProfile && (
                <>
                  <div className="dd-sep" />
                  <div className="dd-account">{userProfile.username}（{userProfile.role}）</div>
                  <button className="dd-item dd-item-danger" onClick={() => void handleLogoutClick()}>
                    <LogOut size={16} /> 登出
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
