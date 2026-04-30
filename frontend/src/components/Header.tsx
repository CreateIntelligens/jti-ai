import { useState } from 'react';
import { RefreshCw, History, KeyRound, Database, Sun, Moon, Loader2 } from 'lucide-react';

import reindexRag from '../services/api/general';

interface HeaderProps {
  status: string;
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
  status,
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
    const confirmed = window.confirm('重新索引所有 RAG 資料？這會重算所有檔案的 embedding，約需 30 秒。');
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
          {sidebarOpen ? '◧' : '◨'}
        </button>
        <h1>File Search Gemini</h1>
        {status && <div className="status" role="status" aria-live="polite">{status}</div>}
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
          <RefreshCw size={14} /> 重新開始
        </button>
        <button
          onClick={onOpenConversationHistory}
          className="header-link secondary"
          aria-label="查看對話歷史"
          disabled={!canOpenConversationHistory}
          title={canOpenConversationHistory ? '查看對話歷史' : '目前沒有可查看歷史的知識庫'}
        >
          <History size={14} /> 對話歷史
        </button>
        <button
          onClick={onOpenUserApiKeySettings}
          className="header-link primary"
          aria-label="設定你的 API Key"
          title={`目前使用中的 Gemini Key：${activeGeminiKeyName}`}
        >
          <KeyRound size={14} /> API Key：{activeGeminiKeyName}
        </button>
        <button
          onClick={handleReindexRag}
          className='header-link secondary'
          aria-label='重新索引 RAG'
          title='重新索引 RAG'
          disabled={isReindexing}
          aria-busy={isReindexing}
        >
          {isReindexing ? (
            <Loader2 size={14} aria-hidden='true'>
              <animateTransform
                attributeName='transform'
                attributeType='XML'
                type='rotate'
                from='0 12 12'
                to='360 12 12'
                dur='1s'
                repeatCount='indefinite'
              />
            </Loader2>
          ) : (
            <RefreshCw size={14} aria-hidden='true' />
          )}
          重新索引 RAG
        </button>
        <button
          onClick={onOpenStoreManagement}
          className="header-link secondary"
          aria-label="開啟知識庫管理"
        >
          <Database size={14} /> 知識庫管理
        </button>
      </div>
    </header>
  );
}
