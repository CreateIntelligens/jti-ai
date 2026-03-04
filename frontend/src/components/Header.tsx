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
        <div 
          className="theme-switch"
          onClick={onToggleTheme}
          role="switch"
          aria-checked={theme === 'light'}
          aria-label="切換深淺色主題"
          tabIndex={0}
          onKeyDown={e => e.key === 'Enter' && onToggleTheme()}
        >
          <span className={`theme-option ${theme === 'dark' ? 'active' : ''}`}>🌙</span>
          <span className={`theme-option ${theme === 'light' ? 'active' : ''}`}>☀️</span>
          <div className={`theme-slider ${theme === 'light' ? 'light' : ''}`} />
        </div>
        <button
          onClick={onRestartChat}
          className="header-link secondary"
          aria-label="重新開始對話"
          disabled={!canRestartChat}
          title={canRestartChat ? '重新開始對話' : '目前沒有可重新開始的知識庫'}
        >
          🔄 重新開始
        </button>
        <button
          onClick={onOpenConversationHistory}
          className="header-link secondary"
          aria-label="查看對話歷史"
          disabled={!canOpenConversationHistory}
          title={canOpenConversationHistory ? '查看對話歷史' : '目前沒有可查看歷史的知識庫'}
        >
          📜 對話歷史
        </button>
        <button
          onClick={onOpenUserApiKeySettings}
          className="header-link primary"
          aria-label="設定你的 API Key"
          title={`目前使用中的 Gemini Key：${activeGeminiKeyName}`}
        >
          ⬢ 專案：{activeGeminiKeyName}
        </button>
        <button
          onClick={onOpenStoreManagement}
          className="header-link secondary"
          aria-label="開啟知識庫管理"
        >
          ⬡ 知識庫管理
        </button>
      </div>
    </header>
  );
}
