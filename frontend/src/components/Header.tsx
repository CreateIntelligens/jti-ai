interface HeaderProps {
  status: string;
  onToggleSidebar: () => void;
  sidebarOpen: boolean;
  onOpenStoreManagement: () => void;
  onOpenAPIKeyManagement: () => void;
  onOpenUserApiKeySettings: () => void;
}

export default function Header({
  status,
  onToggleSidebar,
  sidebarOpen,
  onOpenStoreManagement,
  onOpenAPIKeyManagement,
  onOpenUserApiKeySettings,
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
        <button
          onClick={onOpenUserApiKeySettings}
          className="header-link primary"
          aria-label="設定你的 API Key"
        >
          ⬢ 我的 API Key
        </button>
        <button
          onClick={onOpenStoreManagement}
          className="header-link secondary"
          aria-label="開啟知識庫管理"
        >
          ⬡ 知識庫管理
        </button>
        <button
          onClick={onOpenAPIKeyManagement}
          className="header-link secondary"
          aria-label="開啟 API 金鑰管理"
        >
          ⬢ API 金鑰
        </button>
      </div>
    </header>
  );
}
