import { useState, useEffect } from 'react';
import type { Store } from '../types';
import { useEscapeKey } from '../hooks/useEscapeKey';
import { getKeyInfos } from '../services/api/general';

interface StoreManagementModalProps {
  isOpen: boolean;
  onClose: () => void;
  stores: Store[];
  currentStore: string | null;
  onCreateStore: (name: string, keyIndex: number) => Promise<void>;
  onDeleteStore: (name: string) => Promise<void>;
  onRefresh: () => void;
}

function storeMeta(store: Store): string {
  if (store.managed_app) {
    const language = store.managed_language === 'en' ? 'English' : '中文';
    return `固定 · ${store.managed_app.toUpperCase()} / ${language}`;
  }
  return `一般 · ${store.file_count ?? 0} 個檔案`;
}

export default function StoreManagementModal({
  isOpen,
  onClose,
  stores,
  currentStore,
  onCreateStore,
  onDeleteStore,
  onRefresh,
}: StoreManagementModalProps) {
  const [newStoreName, setNewStoreName] = useState('');
  const [selectedKeyIndex, setSelectedKeyIndex] = useState(0);
  const [keyNames, setKeyNames] = useState<string[]>([]);
  const [creating, setCreating] = useState(false);

  useEscapeKey(onClose, isOpen);

  useEffect(() => {
    if (isOpen) {
      getKeyInfos().then(info => setKeyNames(info.names)).catch(() => setKeyNames([]));
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleCreate = async () => {
    if (!newStoreName.trim()) return;
    setCreating(true);
    try {
      await onCreateStore(newStoreName.trim(), selectedKeyIndex);
      setNewStoreName('');
      onRefresh();
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (store: Store) => {
    if (store.managed_app) return;
    const label = store.display_name || store.name;
    if (!confirm(`確定要刪除知識庫「${label}」嗎？此操作無法復原。`)) {
      return;
    }
    await onDeleteStore(store.name);
  };

  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal app-container store-management-modal" onClick={e => e.stopPropagation()} style={{ maxWidth: '720px' }}>
        <h2>⬡ 知識庫管理</h2>

        <div className="modal-content">
          <div>
            <h3 style={{ fontSize: '1.1rem', marginBottom: '1rem', color: 'var(--crystal-cyan)' }}>
              建立新知識庫
            </h3>
            <div className="flex gap-md">
              <input
                type="text"
                value={newStoreName}
                onChange={e => setNewStoreName(e.target.value)}
                placeholder="輸入知識庫名稱..."
                className="flex-1"
                onKeyDown={e => e.key === 'Enter' && handleCreate()}
              />
              {keyNames.length > 1 && (
                <select
                  value={selectedKeyIndex}
                  onChange={e => setSelectedKeyIndex(Number(e.target.value))}
                  style={{ minWidth: '120px' }}
                  title="選擇這個知識庫使用哪把 Gemini key"
                >
                  {keyNames.map((name, i) => (
                    <option key={i} value={i}>{name}</option>
                  ))}
                </select>
              )}
              <button onClick={handleCreate} disabled={creating || !newStoreName.trim()}>
                {creating ? '建立中...' : '✓ 建立'}
              </button>
            </div>
          </div>

          <div>
            <h3 style={{ fontSize: '1.1rem', marginBottom: '1rem', color: 'var(--crystal-amber)' }}>
              現有知識庫
            </h3>
            {stores.length === 0 ? (
              <p style={{ color: '#8090b0', textAlign: 'center', padding: '2rem 0' }}>
                尚無知識庫
              </p>
            ) : (
              <ul className="file-list">
                {stores.map(store => (
                  <li key={store.name}>
                    <span>
                      {store.display_name || store.name}
                      {store.name === currentStore && (
                        <span style={{ marginLeft: '0.5rem', color: 'var(--crystal-teal)' }}>
                          ◆ 使用中
                        </span>
                      )}
                      <span style={{ display: 'block', color: '#8090b0', fontSize: '0.8em', marginTop: '0.25rem' }}>
                        {storeMeta(store)}
                        {!store.managed_app && keyNames.length > 1 && typeof store.key_index === 'number' && (
                          <> · {keyNames[store.key_index] ?? `Key #${store.key_index + 1}`}</>
                        )}
                      </span>
                    </span>
                    {!store.managed_app && (
                      <button
                        onClick={() => handleDelete(store)}
                        className="danger small"
                        disabled={store.name === currentStore}
                      >
                        ✕ 刪除
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="modal-actions">
          <button onClick={onRefresh} className="secondary">
            重新整理
          </button>
          <button onClick={onClose} className="secondary">
            關閉
          </button>
        </div>
      </div>
    </div>
  );
}
