export default function Header({ status, onToggleSidebar, sidebarOpen, onOpenStoreManagement }) {
  return (
    <header>
      <div className="flex items-center gap-md">
        <button 
          onClick={onToggleSidebar}
          className="secondary"
          style={{ padding: '0.5rem', marginRight: '1rem', fontSize: '1.2rem', lineHeight: 1 }}
          title={sidebarOpen ? "收合側邊欄" : "展開側邊欄"}
        >
          ☰
        </button>
        <h1>Gemini 知識庫助理</h1>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <button
          onClick={onOpenStoreManagement}
          className="secondary"
          style={{ padding: '0.5rem 1rem', fontSize: '0.9rem' }}
          title="管理知識庫"
        >
          ⚙️ 管理知識庫
        </button>
        <div className="status">{status}</div>
      </div>
    </header>
  );
}
