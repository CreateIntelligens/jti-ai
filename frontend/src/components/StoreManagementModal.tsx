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

  const handleDelete = async (storeName: string) => {
    if (!confirm(`確定要刪除知識庫「${storeName}」嗎？此操作無法復原。`)) {
      return;
    }
    await onDeleteStore(storeName);
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
                  title="選擇使用哪個專案 key 建立"
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
                      {keyNames.length > 1 && typeof store.key_index === 'number' && (
                        <span style={{ marginLeft: '0.5rem', color: '#8090b0', fontSize: '0.8em' }}>
                          {keyNames[store.key_index] ?? `Key #${store.key_index + 1}`}
                        </span>
                      )}
                    </span>
                    <button
                      onClick={() => handleDelete(store.name)}
                      className="danger small"
                      disabled={store.name === currentStore}
                    >
                      ✕ 刪除
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="modal-actions">
          <button onClick={onClose} className="secondary">
            關閉
          </button>
        </div>
      </div>
    </div>
  );
}
