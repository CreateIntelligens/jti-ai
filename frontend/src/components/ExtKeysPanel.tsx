import { useState, useEffect } from 'react';
import { Copy, Link2, X } from 'lucide-react';
import * as api from '../services/api';
import type { Store } from '../types';
import { useEscapeKey } from '../hooks/useEscapeKey';

interface ExtKeysPanelProps {
  isOpen: boolean;
  onClose: () => void;
  stores: Store[];
  onShowStatus?: (msg: string) => void;
}

interface APIKey {
  id: string;
  key_prefix: string;
  name: string;
  store_name: string;
  prompt_index: number | null;
  created_at: string;
}

export default function ExtKeysPanel({
  isOpen,
  onClose,
  stores,
  onShowStatus,
}: ExtKeysPanelProps) {
  const [apiKeys, setApiKeys] = useState<APIKey[]>([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [targetStore, setTargetStore] = useState('');
  const [newKeyResult, setNewKeyResult] = useState<string | null>(null);

  useEscapeKey(onClose, isOpen);

  useEffect(() => {
    if (isOpen) {
      loadKeys();
      setNewKeyResult(null);
    }
  }, [isOpen]);

  const loadKeys = async () => {
    setLoading(true);
    try {
      const data = await api.listApiKeys();
      setApiKeys(data);
    } catch {
      setApiKeys([]);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!newKeyName.trim() || !targetStore) return;
    setCreating(true);
    try {
      const result = await api.createApiKey(newKeyName.trim(), targetStore, null);
      setNewKeyResult(result.key);
      setNewKeyName('');
      setTargetStore('');
      await loadKeys();
      onShowStatus?.('✅ API Key 已建立');
    } catch (e) {
      alert('建立失敗: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (keyId: string) => {
    if (!confirm('確定要撤銷此 API Key 嗎？')) return;
    try {
      await api.deleteServerApiKey(keyId);
      await loadKeys();
      onShowStatus?.('API Key 已撤銷');
    } catch (e) {
      alert('撤銷失敗: ' + (e instanceof Error ? e.message : String(e)));
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(() => onShowStatus?.('✅ 已複製'));
  };

  if (!isOpen) return null;

  return (
    <div className="rp-overlay" onClick={onClose}>
      <div className="rp-panel" onClick={(e) => e.stopPropagation()}>
        <div className="rp-header">
          <span className="rp-title">對外 API Keys</span>
          <button className="icon-btn" onClick={onClose}><X size={18} /></button>
        </div>
        <div className="rp-body">
          {/* Create new key */}
          <div>
            <div className="rp-section-title">發行新 Key</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '.5rem' }}>
              <input
                className="input-base"
                placeholder="Key 名稱"
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
              />
              <select
                className="input-base"
                value={targetStore}
                onChange={(e) => setTargetStore(e.target.value)}
              >
                <option value="">選擇目標知識庫...</option>
                {stores.map((s) => (
                  <option key={s.name} value={s.name}>
                    {s.display_name || s.name}
                  </option>
                ))}
              </select>
              <button
                className="btn btn-primary btn-sm"
                style={{ alignSelf: 'flex-start' }}
                onClick={handleCreate}
                disabled={creating || !newKeyName.trim() || !targetStore}
              >
                {creating ? '建立中...' : '發行'}
              </button>
            </div>

            {/* Newly created key */}
            {newKeyResult && (
              <div
                style={{
                  marginTop: '.75rem',
                  padding: '.75rem',
                  background: 'var(--primary-lt)',
                  border: '1px solid var(--primary)',
                  borderRadius: 'var(--r-md)',
                }}
              >
                <div style={{ fontSize: '.8125rem', color: 'var(--primary)', fontWeight: 600, marginBottom: '.375rem' }}>
                  Key 已建立！請立即複製，離開後無法再查看：
                </div>
                <div style={{ display: 'flex', gap: '.375rem', alignItems: 'center' }}>
                  <code
                    style={{
                      flex: 1,
                      fontSize: '.75rem',
                      wordBreak: 'break-all',
                      background: 'var(--bg)',
                      padding: '.375rem .5rem',
                      borderRadius: '.25rem',
                    }}
                  >
                    {newKeyResult}
                  </code>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => copyToClipboard(newKeyResult)}
                    title="複製"
                  >
                    <Copy size={14} />
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="sep-row">
            <div className="sep-line" />
            <span className="sep-label">已發行</span>
            <div className="sep-line" />
          </div>

          {/* Key list */}
          <div>
            {loading ? (
              <div style={{ color: 'var(--text-3)', fontSize: '.875rem' }}>載入中...</div>
            ) : apiKeys.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '1.5rem', color: 'var(--text-3)', fontSize: '.875rem' }}>
                尚無對外 API Key
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '.375rem' }}>
                {apiKeys.map((k) => (
                  <div key={k.id} className="ext-key-row">
                    <Link2 size={14} style={{ color: 'var(--text-3)', flexShrink: 0 }} />
                    <span className="ekr-name">{k.name}</span>
                    <span className="ekr-key">{k.key_prefix}••••</span>
                    <span className="ekr-meta">
                      {stores.find((s) => s.name === k.store_name)?.display_name || k.store_name}
                    </span>
                    <button
                      className="btn btn-danger btn-sm"
                      onClick={() => handleDelete(k.id)}
                      style={{ flexShrink: 0 }}
                    >
                      撤銷
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
