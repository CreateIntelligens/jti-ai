import { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import type { Store } from '../types';
import { getKeyInfos } from '../services/api/general';
import { useEscapeKey } from '../hooks/useEscapeKey';
import { getStoreIcon } from '../utils/storeDisplay';

interface AdminPanelProps {
  isOpen: boolean;
  onClose: () => void;
  stores: Store[];
  currentStore: string | null;
  onCreateStore: (name: string, keyIndex: number) => Promise<void>;
  onDeleteStore: (name: string) => Promise<void>;
  onRefresh: () => void;
}

export default function AdminPanel({
  isOpen,
  onClose,
  stores,
  currentStore,
  onCreateStore,
  onDeleteStore,
  onRefresh,
}: AdminPanelProps) {
  const [keyNames, setKeyNames] = useState<string[]>([]);
  const [newStoreName, setNewStoreName] = useState('');
  const [selectedKeyIndex, setSelectedKeyIndex] = useState('0');
  const [creating, setCreating] = useState(false);

  useEscapeKey(onClose, isOpen);

  useEffect(() => {
    if (isOpen) {
      getKeyInfos()
        .then((info) => setKeyNames(info.names || []))
        .catch(() => setKeyNames([]));
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const effectiveKeyNames = keyNames.length > 0 ? keyNames : ['全部專案'];

  const handleCreate = async () => {
    if (!newStoreName.trim()) return;
    setCreating(true);
    try {
      await onCreateStore(newStoreName.trim(), Number(selectedKeyIndex));
      setNewStoreName('');
      onRefresh();
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (store: Store) => {
    if (store.managed_app) return;
    const label = store.display_name || store.name;
    if (!confirm(`確定要刪除知識庫「${label}」嗎？此操作無法復原。`)) return;
    await onDeleteStore(store.name);
  };

  const storeMeta = (store: Store): string => {
    if (store.managed_app) {
      const lang = store.managed_language === 'en' ? 'English' : '中文';
      return `固定 · ${store.managed_app.toUpperCase()} / ${lang}`;
    }
    return `一般 · ${store.file_count ?? 0} 個檔案`;
  };

  return (
    <div className="rp-overlay" onClick={onClose}>
      <div className="rp-panel" onClick={(e) => e.stopPropagation()}>
        <div className="rp-header">
          <span className="rp-title">知識庫管理</span>
          <button className="icon-btn" onClick={onClose}><X size={18} /></button>
        </div>
        <div className="rp-body">
          {/* Create new store */}
          <div>
            <div className="rp-section-title">新增知識庫</div>
            <div style={{ display: 'flex', gap: '.5rem' }}>
              <input
                className="input-base"
                placeholder="知識庫名稱"
                value={newStoreName}
                onChange={(e) => setNewStoreName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
                style={{ flex: 2 }}
              />
              {effectiveKeyNames.length > 1 && (
                <select
                  className="input-base"
                  value={selectedKeyIndex}
                  onChange={(e) => setSelectedKeyIndex(e.target.value)}
                  style={{ flex: 1 }}
                >
                  {effectiveKeyNames.map((name, i) => (
                    <option key={i} value={String(i)}>{name || `Key #${i + 1}`}</option>
                  ))}
                </select>
              )}
              <button
                className="btn btn-primary btn-sm"
                onClick={handleCreate}
                disabled={creating || !newStoreName.trim()}
              >
                {creating ? '建立中...' : '建立'}
              </button>
            </div>
            {effectiveKeyNames.length > 1 && (
              <div style={{ marginTop: '.5rem', fontSize: '.75rem', color: 'var(--text-3)' }}>
                選擇要使用哪個 Gemini Key（專案）。
              </div>
            )}
          </div>

          {/* Existing stores */}
          <div>
            <div className="rp-section-title">現有知識庫</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '.375rem' }}>
              {stores.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-3)', fontSize: '.875rem' }}>
                  尚無知識庫
                </div>
              ) : (
                stores.map((s) => {
                  const keyName = keyNames.length > 1 && typeof s.key_index === 'number'
                    ? keyNames[s.key_index] || `Key #${s.key_index + 1}`
                    : null;
                  return (
                    <div key={s.name} className="key-card">
                      <div style={{ fontSize: '1.25rem', width: '2rem', textAlign: 'center', flexShrink: 0 }}>
                        {getStoreIcon(s.managed_app || '')}
                      </div>
                      <div className="kc-info">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '.375rem' }}>
                          <span className="kc-name">{s.display_name || s.name}</span>
                          {s.managed_app && <span className="kc-badge system">固定</span>}
                          {s.name === currentStore && <span className="kc-badge system">使用中</span>}
                        </div>
                        <div className="kc-meta">
                          {storeMeta(s)}
                          {keyName && ` · ${keyName}`}
                        </div>
                      </div>
                      {!s.managed_app && (
                        <button
                          className="btn btn-danger btn-sm"
                          onClick={() => handleDelete(s)}
                          disabled={s.name === currentStore}
                        >
                          刪除
                        </button>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
