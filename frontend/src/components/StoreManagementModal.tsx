import { useState, useEffect } from 'react';
import type { Store } from '../types';
import { useEscapeKey } from '../hooks/useEscapeKey';
import { getKeyInfos } from '../services/api/general';
import AppSelect, { type AppSelectOption } from './AppSelect';

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

function formatStoreKeyName(keyName: string | undefined, index: number): string {
  const normalized = keyName?.trim();
  if (normalized) return normalized;
  return `Key #${index + 1}`;
}

export function buildStoreKeyOptions(keyNames: string[]): AppSelectOption[] {
  const names = keyNames.length > 0 ? keyNames : ['全部專案'];
  return names.map((name, i) => ({
    value: String(i),
    label: formatStoreKeyName(name, i),
  }));
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
  const keySelectOptions = buildStoreKeyOptions(keyNames);
  const selectedKeyValue = keySelectOptions.some(option => option.value === String(selectedKeyIndex))
    ? String(selectedKeyIndex)
    : '0';
  const hasMultipleKeyOptions = keyNames.length > 1;

  useEscapeKey(onClose, isOpen);

  useEffect(() => {
    if (isOpen) {
      getKeyInfos()
        .then(info => {
          setKeyNames(info.names);
          setSelectedKeyIndex(current => info.names[current] === undefined ? 0 : current);
        })
        .catch(() => {
          setKeyNames([]);
          setSelectedKeyIndex(0);
        });
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleCreate = async () => {
    if (!newStoreName.trim()) return;
    setCreating(true);
    try {
      await onCreateStore(newStoreName.trim(), Number(selectedKeyValue));
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
            <div className="store-create-row">
              <input
                type="text"
                value={newStoreName}
                onChange={e => setNewStoreName(e.target.value)}
                placeholder="輸入知識庫名稱..."
                className="flex-1"
                onKeyDown={e => e.key === 'Enter' && handleCreate()}
              />
              {hasMultipleKeyOptions ? (
                <AppSelect
                  value={selectedKeyValue}
                  onChange={value => setSelectedKeyIndex(Number(value))}
                  options={keySelectOptions}
                  className="store-key-select"
                  contentClassName="store-key-select-content"
                  title="選擇這個知識庫使用哪把 Gemini key"
                />
              ) : (
                <div className="store-key-static" title="目前只有一個可用專案">
                  {keySelectOptions[0]?.label || '全部專案'}
                </div>
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
                          <> · {formatStoreKeyName(keyNames[store.key_index], store.key_index)}</>
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
