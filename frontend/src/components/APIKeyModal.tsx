import { useState, useEffect } from 'react';
import * as api from '../services/api';
import type { Store } from '../types';

interface APIKey {
  id: string;
  key_prefix: string;
  name: string;
  store_name: string;
  created_at: string;
}

interface APIKeyModalProps {
  isOpen: boolean;
  onClose: () => void;
  stores: Store[];
}

export default function APIKeyModal({ isOpen, onClose, stores }: APIKeyModalProps) {
  const [selectedStore, setSelectedStore] = useState('');
  const [keyName, setKeyName] = useState('');
  const [keys, setKeys] = useState<APIKey[]>([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newKeyCreated, setNewKeyCreated] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      loadKeys();
    } else {
      setNewKeyCreated(null);
    }
  }, [isOpen, selectedStore]);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [isOpen, onClose]);

  const loadKeys = async () => {
    setLoading(true);
    try {
      const data = await api.listApiKeys(selectedStore || undefined);
      setKeys(data);
    } catch (e) {
      console.error('Failed to load API keys:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!selectedStore || !keyName.trim()) return;
    setCreating(true);
    try {
      const result = await api.createApiKey(keyName.trim(), selectedStore);
      setNewKeyCreated(result.key);
      setKeyName('');
      await loadKeys();
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      alert('建立失敗: ' + errorMsg);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (keyId: string) => {
    if (!confirm('確定要刪除此 API Key 嗎？')) return;
    try {
      await api.deleteServerApiKey(keyId);
      await loadKeys();
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      alert('刪除失敗: ' + errorMsg);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>⬢ API 金鑰管理</h2>

        <div className="modal-content">
          {newKeyCreated && (
            <div style={{ 
              padding: '1rem', 
              background: 'var(--crystal-amber)', 
              color: '#0a0f1a', 
              borderRadius: '8px',
              marginBottom: '1rem'
            }}>
              <p style={{ fontWeight: 'bold', marginBottom: '0.5rem' }}>✓ API Key 已建立</p>
              <p style={{ fontSize: '0.9rem', marginBottom: '0.5rem' }}>請妥善保存此金鑰，之後無法再次查看：</p>
              <code style={{ 
                display: 'block', 
                padding: '0.5rem', 
                background: 'rgba(0,0,0,0.2)', 
                borderRadius: '4px',
                wordBreak: 'break-all'
              }}>
                {newKeyCreated}
              </code>
              <button 
                onClick={() => setNewKeyCreated(null)}
                style={{ marginTop: '0.5rem', fontSize: '0.85rem' }}
              >
                我已保存
              </button>
            </div>
          )}

          <div>
            <h3 style={{ fontSize: '1.1rem', marginBottom: '1rem', color: 'var(--crystal-cyan)' }}>
              建立新的 API Key
            </h3>
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.5rem', color: '#8090b0' }}>
                選擇知識庫
              </label>
              <select
                value={selectedStore}
                onChange={e => setSelectedStore(e.target.value)}
                className="w-full"
              >
                <option value="">選擇知識庫...</option>
                {stores.map(store => (
                  <option key={store.name} value={store.name}>
                    {store.display_name || store.name}
                  </option>
                ))}
              </select>
            </div>
            {selectedStore && (
              <div className="flex gap-md">
                <input
                  type="text"
                  value={keyName}
                  onChange={e => setKeyName(e.target.value)}
                  placeholder="輸入用途說明（例如：測試、生產環境）"
                  className="flex-1"
                  onKeyDown={e => e.key === 'Enter' && handleCreate()}
                />
                <button onClick={handleCreate} disabled={creating || !keyName.trim()}>
                  {creating ? '建立中...' : '✓ 建立'}
                </button>
              </div>
            )}
          </div>

          <div>
            <h3 style={{ fontSize: '1.1rem', marginBottom: '1rem', color: 'var(--crystal-amber)' }}>
              現有 API Keys
            </h3>
            {loading ? (
              <p style={{ color: '#8090b0', textAlign: 'center', padding: '2rem 0' }}>
                載入中...
              </p>
            ) : keys.length === 0 ? (
              <p style={{ color: '#8090b0', textAlign: 'center', padding: '2rem 0' }}>
                尚無 API Key
              </p>
            ) : (
              <ul className="file-list">
                {keys.map(key => (
                  <li key={key.id}>
                    <div>
                      <div style={{ fontWeight: 'bold' }}>{key.name}</div>
                      <div style={{ fontSize: '0.85rem', color: '#8090b0' }}>
                        {key.key_prefix} | {stores.find(s => s.name === key.store_name)?.display_name || key.store_name}
                      </div>
                    </div>
                    <button
                      onClick={() => handleDelete(key.id)}
                      className="danger small"
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
