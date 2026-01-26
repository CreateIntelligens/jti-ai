interface HeaderProps {
  status: string;
  onToggleSidebar: () => void;
  sidebarOpen: boolean;
  onOpenStoreManagement: () => void;
  onOpenAPIKeyManagement: () => void;
}

export default function Header({
  status,
  onToggleSidebar,
  sidebarOpen,
  onOpenStoreManagement,
  onOpenAPIKeyManagement,
}: HeaderProps) {
  return (
    <header>
      <div className="header-left">
        <div className="toggle-icon" onClick={onToggleSidebar}>
          {sidebarOpen ? '◧' : '◨'}
        </div>
        <h1>✦ Crystalline Archive</h1>
        {status && <div className="status">{status}</div>}
      </div>
      <div className="header-actions">
        <button
          onClick={onOpenStoreManagement}
          className="header-link secondary"
        >
          ⬡ 知識庫管理
        </button>
        <button
          onClick={onOpenAPIKeyManagement}
          className="header-link secondary"
        >
          ⬢ API 金鑰
        </button>
      </div>
    </header>
  );
}
