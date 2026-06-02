import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Database,
  History,
  KeyRound,
  Link2,
  Loader2,
  Menu,
  MessageSquare,
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
import { isAdminRole } from '../utils/authRouting';

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
  onOpenPromptPanel: () => void;
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
  onOpenPromptPanel,
  onOpenExtKeysPanel,
  onShowStatus,
  userProfile,
  onOpenUsersPanel,
  onLogout,
}: HeaderProps) {
  const navigate = useNavigate();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [isReindexing, setIsReindexing] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  const isAdmin = isAdminRole(userProfile?.role);
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
            <select
              className="select-reset header-app-nav"
              value=""
              title="前往應用"
              aria-label="前往應用"
              onChange={(e) => {
                if (e.target.value) navigate(e.target.value);
              }}
            >
              <option value="" disabled hidden>前往應用</option>
              <option value="/hciot">HCIoT 衛教助手</option>
              <option value="/jti">JTI 智慧助手</option>
            </select>
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
              <button className="dd-item" onClick={() => openPanel(onOpenPromptPanel)}>
                <MessageSquare size={16} /> Prompt 設定
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
            </div>
          )}
        </div>
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
