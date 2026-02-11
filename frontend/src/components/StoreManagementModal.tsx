import { useState, useEffect } from 'react';
import * as api from '../services/api';
import type { Store } from '../types';

interface APIKey {
  id: string;
  key_prefix: string;
  name: string;
  store_name: string;
  prompt_index: number | null;
  created_at: string;
}

interface PromptItem {
  id: string;
  name: string;
  content: string;
  is_active: boolean;
}

interface StoreManagementModalProps {
  isOpen: boolean;
  onClose: () => void;
  stores: Store[];
  currentStore: string | null;
  onCreateStore: (name: string) => Promise<void>;
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
  const [creating, setCreating] = useState(false);

  // API Key 相關狀態
  const [apiKeyStore, setApiKeyStore] = useState('');
  const [apiKeyName, setApiKeyName] = useState('');
  const [apiKeyPromptIndex, setApiKeyPromptIndex] = useState<string>('');
  const [apiKeyPrompts, setApiKeyPrompts] = useState<PromptItem[]>([]);
  const [apiKeys, setApiKeys] = useState<APIKey[]>([]);
  const [apiKeysLoading, setApiKeysLoading] = useState(false);
  const [apiKeyCreating, setApiKeyCreating] = useState(false);
  const [newApiKeyCreated, setNewApiKeyCreated] = useState<string | null>(null);
  const [curlCopied, setCurlCopied] = useState(false);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [isOpen, onClose]);

  // 開啟時載入 API Keys
  useEffect(() => {
    if (isOpen) {
      loadApiKeys();
    } else {
      setNewApiKeyCreated(null);
      setCurlCopied(false);
    }
  }, [isOpen]);

  // 選擇知識庫後載入 prompt 列表
  useEffect(() => {
    if (apiKeyStore) {
      api.listPrompts(apiKeyStore).then(data => {
        setApiKeyPrompts(Array.isArray(data) ? data : []);
      }).catch(() => setApiKeyPrompts([]));
    } else {
      setApiKeyPrompts([]);
    }
    setApiKeyPromptIndex('');
  }, [apiKeyStore]);

  const loadApiKeys = async () => {
    setApiKeysLoading(true);
    try {
      const data = await api.listApiKeys();
      setApiKeys(data);
    } catch (e) {
      console.error('Failed to load API keys:', e);
    } finally {
      setApiKeysLoading(false);
    }
  };

  const handleCreateApiKey = async () => {
    if (!apiKeyStore || !apiKeyName.trim()) return;
    setApiKeyCreating(true);
    try {
      const promptIndex = apiKeyPromptIndex !== '' ? Number(apiKeyPromptIndex) : null;
      const result = await api.createApiKey(apiKeyName.trim(), apiKeyStore, promptIndex);
      setNewApiKeyCreated(result.key);
      setApiKeyName('');
      setApiKeyPromptIndex('');
      setCurlCopied(false);
      await loadApiKeys();
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      alert('建立失敗: ' + errorMsg);
    } finally {
      setApiKeyCreating(false);
    }
  };

  const handleDeleteApiKey = async (keyId: string) => {
    if (!confirm('確定要刪除此 API Key 嗎？')) return;
    try {
      await api.deleteServerApiKey(keyId);
      await loadApiKeys();
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      alert('刪除失敗: ' + errorMsg);
    }
  };

  const getCurlExample = (key: string) => {
    const host = window.location.origin;
    return `curl -X POST ${host}/v1/chat/completions \\
  -H "Authorization: Bearer ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"gemini-2.5-flash-lite","messages":[{"role":"user","content":"你好"}]}'`;
  };

  const handleCopyCurl = async () => {
    if (!newApiKeyCreated) return;
    try {
      await navigator.clipboard.writeText(getCurlExample(newApiKeyCreated));
      setCurlCopied(true);
      setTimeout(() => setCurlCopied(false), 2000);
    } catch {
      // fallback
      const textarea = document.createElement('textarea');
      textarea.value = getCurlExample(newApiKeyCreated);
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCurlCopied(true);
      setTimeout(() => setCurlCopied(false), 2000);
    }
  };

  if (!isOpen) return null;

  const handleCreate = async () => {
    if (!newStoreName.trim()) return;
    setCreating(true);
    try {
      await onCreateStore(newStoreName.trim());
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
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: '720px' }}>
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

          {/* 分隔線 */}
          <div style={{
            height: '1px',
            background: 'linear-gradient(to right, transparent, var(--glass-border), transparent)',
            margin: '0.5rem 0',
          }} />

          {/* API 金鑰管理 */}
          <div>
            <h3 style={{ fontSize: '1.1rem', marginBottom: '1rem', color: 'var(--crystal-cyan)' }}>
              ⬢ API 金鑰管理
            </h3>

            {/* 建立成功提示 + curl 範例 */}
            {newApiKeyCreated && (
              <div style={{
                padding: '1rem',
                background: 'var(--crystal-amber)',
                color: '#0a0f1a',
                borderRadius: '8px',
                marginBottom: '1rem',
              }}>
                <p style={{ fontWeight: 'bold', marginBottom: '0.5rem' }}>✓ API Key 已建立</p>
                <p style={{ fontSize: '0.85rem', marginBottom: '0.5rem' }}>
                  請妥善保存，之後無法再次查看：
                </p>
                <code style={{
                  display: 'block',
                  padding: '0.5rem',
                  background: 'rgba(0,0,0,0.2)',
                  borderRadius: '4px',
                  wordBreak: 'break-all',
                  fontSize: '0.85rem',
                }}>
                  {newApiKeyCreated}
                </code>

                <p style={{ fontWeight: 'bold', marginTop: '1rem', marginBottom: '0.5rem' }}>
                  📋 curl 範例
                </p>
                <pre style={{
                  padding: '0.75rem',
                  background: 'rgba(0,0,0,0.3)',
                  borderRadius: '4px',
                  fontSize: '0.8rem',
                  lineHeight: 1.5,
                  overflowX: 'auto',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-all',
                }}>
                  {getCurlExample(newApiKeyCreated)}
                </pre>
                <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                  <button onClick={handleCopyCurl} style={{ fontSize: '0.85rem' }}>
                    {curlCopied ? '✓ 已複製' : '⧉ 複製 curl'}
                  </button>
                  <button
                    onClick={() => setNewApiKeyCreated(null)}
                    style={{ fontSize: '0.85rem' }}
                  >
                    我已保存
                  </button>
                </div>
              </div>
            )}

            {/* 建立新 API Key */}
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.5rem', color: '#8090b0' }}>
                選擇知識庫
              </label>
              <select
                value={apiKeyStore}
                onChange={e => setApiKeyStore(e.target.value)}
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
            {apiKeyStore && (
              <>
                {apiKeyPrompts.length > 0 && (
                  <div style={{ marginBottom: '1rem' }}>
                    <label style={{ display: 'block', marginBottom: '0.5rem', color: '#8090b0' }}>
                      指定 Prompt（可選）
                    </label>
                    <select
                      value={apiKeyPromptIndex}
                      onChange={e => setApiKeyPromptIndex(e.target.value)}
                      className="w-full"
                    >
                      <option value="">使用預設（啟用中的 Prompt）</option>
                      {apiKeyPrompts.map((p, idx) => (
                        <option key={p.id} value={idx}>
                          {p.name}{p.is_active ? ' (目前啟用)' : ''}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                <div className="flex gap-md">
                  <input
                    type="text"
                    value={apiKeyName}
                    onChange={e => setApiKeyName(e.target.value)}
                    placeholder="用途說明（例如：測試、生產環境）"
                    className="flex-1"
                    onKeyDown={e => e.key === 'Enter' && handleCreateApiKey()}
                  />
                  <button
                    onClick={handleCreateApiKey}
                    disabled={apiKeyCreating || !apiKeyName.trim()}
                  >
                    {apiKeyCreating ? '建立中...' : '✓ 建立'}
                  </button>
                </div>
              </>
            )}
          </div>

          {/* 現有 API Keys */}
          <div>
            <h3 style={{ fontSize: '1.1rem', marginBottom: '1rem', color: 'var(--crystal-amber)' }}>
              現有 API Keys
            </h3>
            {apiKeysLoading ? (
              <p style={{ color: '#8090b0', textAlign: 'center', padding: '1rem 0' }}>
                載入中...
              </p>
            ) : apiKeys.length === 0 ? (
              <p style={{ color: '#8090b0', textAlign: 'center', padding: '1rem 0' }}>
                尚無 API Key
              </p>
            ) : (
              <ul className="file-list">
                {apiKeys.map(key => (
                  <li key={key.id}>
                    <div>
                      <div style={{ fontWeight: 'bold' }}>{key.name}</div>
                      <div style={{ fontSize: '0.85rem', color: '#8090b0' }}>
                        {key.key_prefix} | {stores.find(s => s.name === key.store_name)?.display_name || key.store_name}
                      </div>
                    </div>
                    <button
                      onClick={() => handleDeleteApiKey(key.id)}
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
