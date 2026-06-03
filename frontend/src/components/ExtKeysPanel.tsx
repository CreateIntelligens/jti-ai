import { useEffect, useMemo, useState } from 'react';
import { Copy, Eye, Link2, X } from 'lucide-react';
import * as api from '../services/api';
import type { Store } from '../types';
import { useEscapeKey } from '../hooks/useEscapeKey';
import { useOverlayPressClose } from '../hooks/useOverlayPressClose';
import { toErrorMessage } from '../utils/errors';
import AppSelect from './AppSelect';

interface ExtKeysPanelProps {
  isOpen: boolean;
  onClose: () => void;
  stores: Store[];
  isAdmin: boolean;
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
    if (!document.execCommand('copy')) {
      throw new Error('execCommand copy failed');
    }
  } finally {
    document.body.removeChild(textarea);
  }
}

export default function ExtKeysPanel({
  isOpen,
  onClose,
  stores,
  isAdmin,
  onShowStatus,
}: ExtKeysPanelProps) {
  const [apiKeys, setApiKeys] = useState<APIKey[]>([]);
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
    () => new Map(stores.map((s) => [s.name, s.display_name || s.name])),
    [stores],
  );
  const storeOptions = [
    { value: '', label: '選擇目標知識庫...' },
    ...stores.map((s) => ({
      value: s.name,
      label: s.display_name || s.name,
    })),
  ];

  useEffect(() => {
    if (isOpen) {
      loadKeys();
      setNewKeyResult(null);
      setRevealedKeys({});
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
    const trimmedName = newKeyName.trim();
    if (!trimmedName || !targetStore) return;
    setCreating(true);
    try {
      const result = await api.createApiKey(trimmedName, targetStore, null);
      setNewKeyResult(result.key);
      setNewKeyName('');
      setTargetStore('');
      await loadKeys();
      onShowStatus?.('✅ API Key 已建立');
    } catch (e) {
      alert('建立失敗: ' + (toErrorMessage(e)));
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
      alert('撤銷失敗: ' + (toErrorMessage(e)));
    }
  };

  const hideRevealedKey = (keyId: string) => {
    setRevealedKeys((prev) => {
      const next = { ...prev };
      delete next[keyId];
      return next;
    });
  };

  const handleReveal = async (keyId: string) => {
    if (revealedKeys[keyId]) {
      hideRevealedKey(keyId);
      return;
    }
    if (!confirm('注意：您正在檢視敏感金鑰，請確保周圍無人窺視。確定要顯示完整金鑰嗎？')) return;
    setRevealingId(keyId);
    try {
      const plain = await api.revealApiKey(keyId);
      setRevealedKeys((prev) => ({ ...prev, [keyId]: plain }));
    } catch (e) {
      alert('讀取失敗: ' + toErrorMessage(e));
    } finally {
      setRevealingId(null);
    }
  };

  const copyToClipboard = async (text: string) => {
    try {
      await writeClipboard(text);
      onShowStatus?.('✅ 已複製');
    } catch {
      onShowStatus?.('❌ 複製失敗，請手動複製');
    }
  };

  const apiBase = 'http://<IP>:8913';
  const curlExample = [
    '# 1) 開啟對話 session，取得 session_id',
    `curl -X POST "${apiBase}/api/chat/start" \\`,
    '  -H "Authorization: Bearer sk-xxxxxxxx" \\',
    '  -H "Content-Type: application/json" -d \'{}\'',
    '',
    '# 2) 送出訊息（SID 換成上一步拿到的 session_id）',
    `curl -X POST "${apiBase}/api/chat/message" \\`,
    '  -H "Authorization: Bearer sk-xxxxxxxx" \\',
    '  -H "Content-Type: application/json" \\',
    '  -d \'{"message":"你好","session_id":"SID"}\'',
  ].join('\n');

  if (!isOpen) return null;

  return (
    <div className="rp-overlay" {...overlayPressClose}>
      <div className="rp-panel" onClick={(e) => e.stopPropagation()}>
        <div className="rp-header">
          <span className="rp-title">對外 API Keys</span>
          <button className="icon-btn" onClick={onClose}><X size={18} /></button>
        </div>
        <div className="rp-body">
          {/* Create new key（僅 admin 可發行；user 為唯讀） */}
          {isAdmin && (
            <>
              <div>
                <div className="rp-section-title">發行新 Key</div>
                <div className="rp-form-stack">
                  <input
                    className="input-base"
                    placeholder="Key 名稱"
                    value={newKeyName}
                    onChange={(e) => setNewKeyName(e.target.value)}
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
                    {creating ? '建立中...' : '發行'}
                  </button>
                </div>

                {/* Newly created key */}
                {newKeyResult && (
                  <div className="rp-key-result">
                    <div className="rp-key-result-label">
                      Key 已建立！
                    </div>
                    <div className="rp-key-result-row">
                      <code className="rp-key-result-code">
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
            </>
          )}

          {/* Key list */}
          <div>
            {loading ? (
              <div className="rp-loading">載入中...</div>
            ) : apiKeys.length === 0 ? (
              <div className="rp-list-empty">
                尚無對外 API Key
              </div>
            ) : (
              <div className="rp-list">
                {apiKeys.map((k) => {
                  const revealedKey = revealedKeys[k.id];
                  return (
                    <div key={k.id} className="ext-key-row">
                      <Link2 className="ekr-icon" size={14} />
                      <span className="ekr-name">{k.name}</span>
                      {revealedKey ? (
                        <code className="ekr-key">{revealedKey}</code>
                      ) : (
                        <span className="ekr-key">{k.key_prefix}••••</span>
                      )}
                      <button
                        className="btn btn-ghost btn-sm shrink-0"
                        onClick={() => handleReveal(k.id)}
                        disabled={revealingId === k.id}
                        title={revealedKey ? '隱藏金鑰' : '顯示完整金鑰'}
                      >
                        <Eye size={14} />
                      </button>
                      {revealedKey && (
                        <button
                          className="btn btn-ghost btn-sm shrink-0"
                          onClick={() => copyToClipboard(revealedKey)}
                          title="複製"
                        >
                          <Copy size={14} />
                        </button>
                      )}
                      <span className="ekr-meta">
                        {storeLabelByName.get(k.store_name) || k.store_name}
                      </span>
                      {isAdmin && (
                        <button
                          className="btn btn-danger btn-sm shrink-0"
                          onClick={() => handleDelete(k.id)}
                        >
                          撤銷
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* 如何使用（curl 範例，佔位符 sk-xxxxxxxx） */}
          <details className="ext-howto">
            <summary>如何使用這把 Key（curl 範例）</summary>
            <div className="ext-howto-body">
              <div className="ext-howto-hint">
                把 <code>sk-xxxxxxxx</code> 換成你上方複製的金鑰即可呼叫。
              </div>
              <div className="rp-key-result-row">
                <pre className="ext-howto-code">{curlExample}</pre>
                <button
                  className="btn btn-ghost btn-sm shrink-0"
                  onClick={() => copyToClipboard(curlExample)}
                  title="複製範例"
                >
                  <Copy size={14} />
                </button>
              </div>
            </div>
          </details>
        </div>
      </div>
    </div>
  );
}
