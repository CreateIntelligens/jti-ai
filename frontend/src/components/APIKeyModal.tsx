import { useState, useEffect } from 'react';
import * as api from '../services/api';
import type { Store } from '../types';

interface APIKeyModalProps {
  isOpen: boolean;
  onClose: () => void;
  stores: Store[];
}

export default function APIKeyModal({ isOpen, onClose, stores }: APIKeyModalProps) {
  const [selectedStore, setSelectedStore] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (isOpen && selectedStore) {
      loadApiKey();
    } else {
      setApiKey('');
    }
  }, [isOpen, selectedStore]);

  const loadApiKey = async () => {
    if (!selectedStore) return;
    setLoading(true);
    try {
      const data = await api.getApiKey(selectedStore);
      setApiKey(data.api_key || '');
    } catch (e) {
      console.error('Failed to load API key:', e);
      setApiKey('');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!selectedStore || !apiKey.trim()) return;
    setSaving(true);
    try {
      await api.saveApiKey(selectedStore, apiKey.trim());
      alert('API 金鑰已儲存!');
      onClose();
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      alert('儲存失敗: ' + errorMsg);
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>⬢ API 金鑰管理</h2>

        <div className="modal-content">
          <div>
            <label style={{ display: 'block', marginBottom: '0.75rem', color: 'var(--crystal-cyan)' }}>
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
            loading ? (
              <p style={{ color: 'var(--crystal-amber)', textAlign: 'center', padding: '2rem 0' }}>
                載入中...
              </p>
            ) : (
              <div>
                <label style={{ display: 'block', marginBottom: '0.75rem', color: 'var(--crystal-cyan)' }}>
                  Gemini API 金鑰
                </label>
                <input
                  type="password"
                  value={apiKey}
                  onChange={e => setApiKey(e.target.value)}
                  placeholder="輸入 Gemini API 金鑰..."
                  className="w-full"
                />
                <p style={{ fontSize: '0.85rem', color: '#8090b0', marginTop: '0.5rem' }}>
                  每個知識庫可設定不同的 API 金鑰
                </p>
              </div>
            )
          )}
        </div>

        <div className="modal-actions">
          <button onClick={onClose} className="secondary">
            取消
          </button>
          {selectedStore && !loading && (
            <button onClick={handleSave} disabled={saving || !apiKey.trim()}>
              {saving ? '儲存中...' : '✓ 儲存'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
