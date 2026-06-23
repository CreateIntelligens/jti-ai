import { useEffect, useMemo, useState } from 'react';
import { Copy, Eye, KeyRound, X } from 'lucide-react';
import * as api from '../services/api';
import type { Store } from '../types';
import { useEscapeKey } from '../hooks/useEscapeKey';
import { useOverlayPressClose } from '../hooks/useOverlayPressClose';
import { toErrorMessage } from '../utils/errors';
import AppSelect from './AppSelect';

interface ApiKeysPanelProps {
  isOpen: boolean;
  onClose: () => void;
  stores: Store[];
  isAdmin: boolean;
  onShowStatus?: (msg: string) => void;
}

interface ServerApiKey {
  id: string;
  key_prefix: string;
  name: string;
  store_name: string;
  prompt_index: number | null;
  created_at: string;
}

async function writeClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  try {
    textarea.focus();
    textarea.select();
    if (!document.execCommand('copy')) throw new Error('copy failed');
  } finally {
    document.body.removeChild(textarea);
  }
}

export default function ApiKeysPanel({
  isOpen,
  onClose,
  stores,
  isAdmin,
  onShowStatus,
}: ApiKeysPanelProps) {
  const [apiKeys, setApiKeys] = useState<ServerApiKey[]>([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [targetStore, setTargetStore] = useState('');
  const [newKeyResult, setNewKeyResult] = useState<string | null>(null);
  const [revealedKeys, setRevealedKeys] = useState<Record<string, string>>({});
  const [revealingId, setRevealingId] = useState<string | null>(null);
  const overlayPressClose = useOverlayPressClose(onClose);

  useEscapeKey(onClose, isOpen);

  const storeLabelByName = useMemo(
    () => new Map(stores.map((store) => [store.name, store.display_name || store.name])),
    [stores],
  );
  const storeOptions = [
    { value: '', label: '選擇目標知識庫' },
    ...stores.map((store) => ({
      value: store.name,
      label: store.display_name || store.name,
    })),
  ];

  const loadKeys = async () => {
    setLoading(true);
    try {
      setApiKeys(await api.listApiKeys());
    } catch {
      setApiKeys([]);
      onShowStatus?.('無法載入 API Keys');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!isOpen) return;
    void loadKeys();
    setNewKeyResult(null);
    setRevealedKeys({});
  }, [isOpen]);

  const copyToClipboard = async (text: string) => {
    try {
      await writeClipboard(text);
      onShowStatus?.('✅ 已複製');
    } catch {
      onShowStatus?.('複製失敗，請手動複製');
    }
  };

  const handleCreate = async () => {
    const name = newKeyName.trim();
    if (!name || !targetStore) return;
    setCreating(true);
    try {
      const result = await api.createApiKey(name, targetStore, null);
      setNewKeyResult(result.key);
      setNewKeyName('');
      setTargetStore('');
      await loadKeys();
      onShowStatus?.('✅ API Key 已建立');
    } catch (error) {
      alert('建立失敗：' + toErrorMessage(error));
    } finally {
      setCreating(false);
    }
  };

  const handleReveal = async (keyId: string) => {
    if (revealedKeys[keyId]) {
      setRevealedKeys((previous) => {
        const next = { ...previous };
        delete next[keyId];
        return next;
      });
      return;
    }
    if (!confirm('即將顯示完整金鑰，請確認周圍無人窺視。是否繼續？')) return;
    setRevealingId(keyId);
    try {
      const key = await api.revealApiKey(keyId);
      setRevealedKeys((previous) => ({ ...previous, [keyId]: key }));
    } catch (error) {
      alert('讀取失敗：' + toErrorMessage(error));
    } finally {
      setRevealingId(null);
    }
  };

  const handleDelete = async (keyId: string) => {
    if (!confirm('確定要撤銷此 API Key 嗎？')) return;
    try {
      await api.deleteServerApiKey(keyId);
      await loadKeys();
      onShowStatus?.('API Key 已撤銷');
    } catch (error) {
      alert('撤銷失敗：' + toErrorMessage(error));
    }
  };

  if (!isOpen) return null;

  return (
    <div className="rp-overlay" {...overlayPressClose}>
      <div className="rp-panel" onClick={(event) => event.stopPropagation()}>
        <div className="rp-header">
          <span className="rp-title">API Key 管理</span>
          <button className="icon-btn" onClick={onClose} aria-label="關閉 API Key 管理">
            <X size={18} />
          </button>
        </div>
        <div className="rp-body">
          {isAdmin && (
            <div>
              <div className="rp-section-title">建立新 Key</div>
              <div className="rp-form-stack">
                <input
                  className="input-base"
                  placeholder="Key 名稱"
                  value={newKeyName}
                  onChange={(event) => setNewKeyName(event.target.value)}
                />
                <AppSelect
                  className="input-base"
                  value={targetStore}
                  onChange={setTargetStore}
                  options={storeOptions}
                  disabled={creating}
                />
                <button
                  className="btn btn-primary btn-sm self-start"
                  onClick={handleCreate}
                  disabled={creating || !newKeyName.trim() || !targetStore}
                >
                  {creating ? '建立中…' : '建立 Key'}
                </button>
              </div>
              {newKeyResult && (
                <div className="rp-key-result">
                  <div className="rp-key-result-label">請立即保存，此金鑰只顯示一次</div>
                  <div className="rp-key-result-row">
                    <code className="rp-key-result-code">{newKeyResult}</code>
                    <button className="btn btn-ghost btn-sm" onClick={() => copyToClipboard(newKeyResult)}>
                      <Copy size={14} /> 複製
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          <div>
            <div className="rp-section-title">已建立的 Keys</div>
            {loading ? (
              <div className="rp-loading">載入中…</div>
            ) : apiKeys.length === 0 ? (
              <div className="rp-list-empty">尚無 API Key</div>
            ) : (
              <div className="rp-list">
                {apiKeys.map((keyInfo) => {
                  const revealedKey = revealedKeys[keyInfo.id];
                  return (
                    <div key={keyInfo.id} className="key-card server-key-card">
                      <div className="kc-icon kc-icon-system"><KeyRound size={16} /></div>
                      <div className="kc-info">
                        <div className="kc-name">{keyInfo.name}</div>
                        <div className="kc-meta">
                          {storeLabelByName.get(keyInfo.store_name) || keyInfo.store_name}
                        </div>
                        <code className="server-key-code">
                          {revealedKey || `${keyInfo.key_prefix}••••`}
                        </code>
                      </div>
                      <div className="rp-card-actions server-key-actions">
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() => handleReveal(keyInfo.id)}
                          disabled={revealingId === keyInfo.id}
                        >
                          <Eye size={14} /> {revealedKey ? '隱藏' : '顯示'}
                        </button>
                        {revealedKey && (
                          <button className="btn btn-ghost btn-sm" onClick={() => copyToClipboard(revealedKey)}>
                            <Copy size={14} /> 複製
                          </button>
                        )}
                        {isAdmin && (
                          <button className="btn btn-danger btn-sm" onClick={() => handleDelete(keyInfo.id)}>
                            撤銷
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
