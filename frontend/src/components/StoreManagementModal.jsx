import { useState } from 'react';

// 格式化 Store 顯示名稱
const formatStoreName = (store) => {
  const displayName = store.display_name || '未命名';
  const id = store.name.split('/').pop() || '';
  const shortId = id.slice(0, 8);
  return `${displayName} (${shortId})`;
};

// 取得簡短 ID
const getShortId = (storeName) => {
  const id = storeName.split('/').pop() || '';
  return id.slice(0, 8);
};

export default function StoreManagementModal({ 
  isOpen, 
  onClose, 
  stores, 
  currentStore,
  onCreateStore, 
  onDeleteStore,
  onRefresh 
}) {
  const [newStoreName, setNewStoreName] = useState('');
  const [deleteConfirm, setDeleteConfirm] = useState('');

  if (!isOpen) return null;

  const handleCreate = async () => {
    if (!newStoreName.trim()) return;
    await onCreateStore(newStoreName.trim());
    setNewStoreName('');
  };

  const handleDelete = async (storeName) => {
    if (deleteConfirm !== storeName) {
      alert('請輸入正確的知識庫名稱以確認刪除');
      return;
    }
    await onDeleteStore(storeName);
    setDeleteConfirm('');
  };

  return (
    <div 
      className="modal-overlay" 
      onClick={onClose}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000
      }}
    >
      <div 
        className="modal-content"
        onClick={(e) => e.stopPropagation()}
        style={{
          backgroundColor: 'white',
          borderRadius: '8px',
          padding: '2rem',
          width: '90%',
          maxWidth: '600px',
          maxHeight: '80vh',
          overflow: 'auto',
          boxShadow: '0 4px 20px rgba(0,0,0,0.15)'
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
          <h2 style={{ margin: 0, fontSize: '1.5rem' }}>📚 知識庫管理</h2>
          <button 
            onClick={onClose}
            style={{ 
              background: 'none', 
              border: 'none', 
              fontSize: '1.5rem', 
              cursor: 'pointer',
              color: '#666',
              padding: '0.25rem 0.5rem'
            }}
          >
            ×
          </button>
        </div>

        {/* 新增知識庫 */}
        <section style={{ marginBottom: '2rem', paddingBottom: '1.5rem', borderBottom: '1px solid #eee' }}>
          <h3 style={{ fontSize: '1.1rem', marginBottom: '1rem', color: '#333' }}>新增知識庫</h3>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <input
              type="text"
              placeholder="輸入知識庫名稱"
              value={newStoreName}
              onChange={(e) => setNewStoreName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
              style={{ 
                flex: 1, 
                padding: '0.75rem', 
                border: '1px solid #ddd', 
                borderRadius: '4px',
                fontSize: '1rem'
              }}
            />
            <button 
              onClick={handleCreate}
              disabled={!newStoreName.trim()}
              style={{ 
                padding: '0.75rem 1.5rem',
                backgroundColor: '#4CAF50',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: newStoreName.trim() ? 'pointer' : 'not-allowed',
                opacity: newStoreName.trim() ? 1 : 0.5,
                fontSize: '1rem',
                fontWeight: 500
              }}
            >
              建立
            </button>
          </div>
        </section>

        {/* 現有知識庫列表 */}
        <section>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3 style={{ fontSize: '1.1rem', margin: 0, color: '#333' }}>現有知識庫</h3>
            <button 
              onClick={onRefresh}
              style={{
                padding: '0.4rem 0.8rem',
                backgroundColor: '#f5f5f5',
                border: '1px solid #ddd',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '0.9rem'
              }}
            >
              ↻ 重新整理
            </button>
          </div>

          {stores.length === 0 ? (
            <p style={{ color: '#999', fontStyle: 'italic', textAlign: 'center', padding: '2rem' }}>
              尚無知識庫
            </p>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              {stores.map(store => (
                <li 
                  key={store.name}
                  style={{
                    padding: '1rem',
                    marginBottom: '0.5rem',
                    backgroundColor: currentStore === store.name ? '#e3f2fd' : '#f9f9f9',
                    borderRadius: '6px',
                    border: currentStore === store.name ? '2px solid #2196F3' : '1px solid #eee'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <div>
                      <strong style={{ fontSize: '1rem' }}>{formatStoreName(store)}</strong>
                      {currentStore === store.name && (
                        <span style={{ 
                          marginLeft: '0.5rem', 
                          fontSize: '0.75rem', 
                          color: '#2196F3',
                          fontWeight: 600
                        }}>
                          (使用中)
                        </span>
                      )}
                      <div style={{ fontSize: '0.8rem', color: '#999', marginTop: '0.25rem' }}>
                        ID: {store.name}
                      </div>
                    </div>
                  </div>
                  
                  {/* 刪除區域 */}
                  <details style={{ fontSize: '0.9rem' }}>
                    <summary 
                      style={{ 
                        cursor: 'pointer', 
                        color: '#d32f2f', 
                        userSelect: 'none',
                        fontWeight: 500
                      }}
                    >
                      刪除此知識庫
                    </summary>
                    <div style={{ marginTop: '0.75rem', paddingTop: '0.75rem', borderTop: '1px solid #ffebee' }}>
                      <p style={{ margin: '0 0 0.5rem 0', fontSize: '0.85rem', color: '#666' }}>
                        請輸入知識庫名稱 <code style={{ backgroundColor: '#ffe0e0', padding: '2px 6px', borderRadius: '3px' }}>{store.name}</code> 以確認刪除：
                      </p>
                      <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <input
                          type="text"
                          placeholder={store.name}
                          value={deleteConfirm}
                          onChange={(e) => setDeleteConfirm(e.target.value)}
                          style={{ 
                            flex: 1, 
                            padding: '0.5rem', 
                            border: '1px solid #ddd', 
                            borderRadius: '4px',
                            fontSize: '0.9rem'
                          }}
                        />
                        <button 
                          onClick={() => handleDelete(store.name)}
                          disabled={deleteConfirm !== store.name}
                          style={{ 
                            padding: '0.5rem 1rem',
                            backgroundColor: '#d32f2f',
                            color: 'white',
                            border: 'none',
                            borderRadius: '4px',
                            cursor: deleteConfirm === store.name ? 'pointer' : 'not-allowed',
                            opacity: deleteConfirm === store.name ? 1 : 0.5,
                            fontSize: '0.9rem',
                            fontWeight: 500
                          }}
                        >
                          確認刪除
                        </button>
                      </div>
                    </div>
                  </details>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
