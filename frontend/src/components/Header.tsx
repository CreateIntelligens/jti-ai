import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Database,
  DatabaseBackup,
  DatabaseZap,
  History,
  KeyRound,
  Link2,
  Loader2,
  Menu,
  Moon,
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
import AppSelect from './AppSelect';

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
  onShowStatus: (msg: string) => void;
  userProfile?: api.UserProfile | null;
  onOpenUsersPanel?: () => void;
  onLogout?: () => void;
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
  onShowStatus,
  userProfile,
  onOpenUsersPanel,
  onLogout,
}: HeaderProps) {
  const navigate = useNavigate();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [isReindexing, setIsReindexing] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  const isAdmin = isAdminRole(userProfile?.role);
  const isSuper = isSuperAdmin(userProfile?.role);
  const handleLogoutClick = useLogoutRedirect(onLogout);

  const openPanel = (openFn: () => void) => {
    openFn();
    setSettingsOpen(false);
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
    <header
      className="app-header"
      onClick={() => settingsOpen && setSettingsOpen(false)}
    >
      <div className="header-left">
        <button
          className="sidebar-toggle"
          onClick={onToggleSidebar}
          aria-label={sidebarOpen ? '關閉側邊欄' : '開啟側邊欄'}
        >
          <Menu size={18} />
        </button>
        <div className="app-logo">
          AI360 <span>Knowledge</span>
        </div>
        {status && <div className="status-badge">{status}</div>}
      </div>

      <div className="header-right">
        {isAdmin && (
          <>
            <AppSelect
              className="header-app-nav"
              value=""
              onChange={(val) => {
                if (val) navigate(val);
              }}
              placeholder="前往應用"
              options={[
                { value: '/', label: 'ai360 km 通用知識庫' },
                { value: '/hciot', label: 'HCIoT 衛教助手' },
                { value: '/jti', label: 'JTI 智慧助手' },
              ]}
            />
            {onOpenUsersPanel && (
              <button
                className="icon-btn"
                onClick={onOpenUsersPanel}
                title="帳號管理"
              >
                <Users size={18} />
              </button>
            )}
          </>
        )}
        <button
          className="icon-btn"
          title="對話歷史"
          disabled={!canOpenConversationHistory}
          onClick={onOpenConversationHistory}
        >
          <History size={18} />
        </button>
        <button
          className="icon-btn"
          onClick={onToggleTheme}
          title={theme === 'dark' ? '切換為淺色主題' : '切換為深色主題'}
        >
          {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
        </button>
        <button
          className="icon-btn icon-btn-pill"
          onClick={() => openPanel(onOpenExtKeysPanel)}
          title="對外 API Keys"
        >
          <Link2 size={16} /> 對外 Keys
        </button>
        {isAdmin && (
          <>
            <div
              className="dd-wrap"
              ref={wrapRef}
              onClick={(e) => e.stopPropagation()}
            >
              <button
                className="icon-btn"
                onClick={() => setSettingsOpen((o) => !o)}
                title="設定"
              >
                <Settings size={16} />
              </button>
              {settingsOpen && (
                <div className="dd-menu">
                  <button className="dd-item" onClick={() => openPanel(onOpenAdminPanel)}>
                    <Database size={16} /> 知識庫管理
                  </button>
                  <button className="dd-item" onClick={() => openPanel(onOpenApiKeysPanel)}>
                    <KeyRound size={16} /> API Key 設定
                  </button>
                  <div className="dd-sep" />
                  <button
                    className="dd-item"
                    onClick={handleReindexRag}
                    disabled={isReindexing}
                  >
                    {isReindexing ? <Loader2 size={16} /> : <RefreshCw size={16} />}
                    重新索引 RAG
                  </button>
                  {isSuper && (
                    <>
                      <button
                        className="dd-item"
                        onClick={handleGlobalDbSync}
                        disabled={isSyncing}
                        title="全域同步（所有應用 + 系統設定）至備援庫"
                      >
                        {isSyncing ? <Loader2 size={16} /> : <DatabaseBackup size={16} />}
                        全域同步至備援庫
                      </button>
                      <button
                        className="dd-item"
                        onClick={handleReverseRestore}
                        disabled={isSyncing}
                        title="災後從備援庫補回主庫（AWS 為主，只補不覆蓋；先預演再確認）"
                      >
                        {isSyncing ? <Loader2 size={16} /> : <DatabaseZap size={16} />}
                        從備援庫補回主庫
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
          </>
        )}
        {userProfile && (
          <>
            <span className="profile-badge">
              {userProfile.username} ({userProfile.role})
            </span>
            <button
              className="icon-btn"
              onClick={() => void handleLogoutClick()}
              title="登出"
            >
              <LogOut size={18} />
            </button>
          </>
        )}
      </div>
    </header>
  );
}
