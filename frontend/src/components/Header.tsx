import { useState } from 'react';
import {
  Database,
  History,
  KeyRound,
  Loader2,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  RefreshCw,
  Sun,
} from 'lucide-react';

import reindexRag from '../services/api/general';

interface HeaderProps {
  onToggleSidebar: () => void;
  sidebarOpen: boolean;
  onOpenStoreManagement: () => void;
  onOpenUserApiKeySettings: () => void;
  activeGeminiKeyName: string;
  onOpenConversationHistory: () => void;
  onRestartChat: () => void;
  canOpenConversationHistory: boolean;
  canRestartChat: boolean;
  theme: 'dark' | 'light';
  onToggleTheme: () => void;
}

export default function Header({
  onToggleSidebar,
  sidebarOpen,
  onOpenStoreManagement,
  onOpenUserApiKeySettings,
  activeGeminiKeyName,
  onOpenConversationHistory,
  onRestartChat,
  canOpenConversationHistory,
  canRestartChat,
  theme,
  onToggleTheme,
}: HeaderProps) {
  const [isReindexing, setIsReindexing] = useState(false);

  const handleReindexRag = async () => {
    if (isReindexing) return;
    const confirmed = window.confirm('重建知識庫索引會重新整理 embedding，期間服務可能暫停約 1 分鐘。是否繼續？');
    if (!confirmed) return;

    setIsReindexing(true);
    try {
      await reindexRag('all');
      window.alert('重新索引已啟動，請稍待');
    } catch (error) {
      window.alert(error instanceof Error ? error.message : '重新索引失敗');
    } finally {
      setIsReindexing(false);
    }
  };

  return (
    <header>
      <div className="header-left">
        <button
          className="toggle-icon"
          onClick={onToggleSidebar}
          aria-label={sidebarOpen ? '關閉側邊欄' : '開啟側邊欄'}
          aria-expanded={sidebarOpen}
        >
          {sidebarOpen ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
        </button>
        <h1>AI360 Knowledge Base</h1>
      </div>
      <div className="header-actions">
        <button
          className={`header-icon-btn theme-toggle-btn ${theme}`}
          onClick={onToggleTheme}
          aria-label={theme === 'dark' ? '切換為淺色主題' : '切換為深色主題'}
          title={theme === 'dark' ? '切換為淺色主題' : '切換為深色主題'}
        >
          <div className="theme-icon-wrapper">
            <Sun className="icon-sun" size={18} />
            <Moon className="icon-moon" size={18} />
          </div>
        </button>
        <button
          onClick={onRestartChat}
          className="header-link secondary"
          aria-label="重新開始對話"
          disabled={!canRestartChat}
          title={canRestartChat ? '重新開始對話' : '目前沒有可重新開始的知識庫'}
        >
          <RefreshCw size={14} />
          <span className="header-link-label">重新開始</span>
        </button>
        <button
          onClick={onOpenConversationHistory}
          className="header-link secondary"
          aria-label="查看對話歷史"
          disabled={!canOpenConversationHistory}
          title={canOpenConversationHistory ? '查看對話歷史' : '目前沒有可查看歷史的知識庫'}
        >
          <History size={14} />
          <span className="header-link-label">歷史</span>
        </button>
        <button
          onClick={onOpenUserApiKeySettings}
          className="header-link primary"
          aria-label="設定你的 API Key"
          title={`目前使用中的 Gemini Key：${activeGeminiKeyName}`}
        >
          <KeyRound size={14} />
          <span className="header-link-label">Key：{activeGeminiKeyName}</span>
        </button>
        <button
          onClick={handleReindexRag}
          className="header-link secondary"
          aria-label="重建索引"
          title="重建知識庫索引"
          disabled={isReindexing}
          aria-busy={isReindexing}
        >
          {isReindexing ? (
            <Loader2 size={14} aria-hidden="true">
              <animateTransform
                attributeName="transform"
                attributeType="XML"
                type="rotate"
                from="0 12 12"
                to="360 12 12"
                dur="1s"
                repeatCount="indefinite"
              />
            </Loader2>
          ) : (
            <RefreshCw size={14} aria-hidden="true" />
          )}
          <span className="header-link-label">重建索引</span>
        </button>
        <button
          onClick={onOpenStoreManagement}
          className="header-link secondary"
          aria-label="開啟知識庫管理"
        >
          <Database size={14} />
          <span className="header-link-label">知識庫</span>
        </button>
      </div>
    </header>
  );
}
