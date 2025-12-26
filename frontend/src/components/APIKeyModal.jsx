import { useState, useEffect } from 'react';
import * as api from '../services/api';
import '../styles/Modal.css';

export default function APIKeyModal({ isOpen, onClose, stores }) {
  const [keys, setKeys] = useState([]);
  const [loading, setLoading] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [newKeyStore, setNewKeyStore] = useState('');
  const [newKeyPromptIndex, setNewKeyPromptIndex] = useState('');
  const [createdKey, setCreatedKey] = useState(null);
  const [copied, setCopied] = useState(false);
  const [copiedCurl, setCopiedCurl] = useState(false);

  useEffect(() => {
    if (isOpen) {
      loadKeys();
      setCreatedKey(null);
    }
  }, [isOpen]);

  const loadKeys = async () => {
    setLoading(true);
    try {
      const data = await api.fetchAPIKeys();
      setKeys(data);
    } catch (e) {
      console.error('Failed to load API keys:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!newKeyName.trim() || !newKeyStore) return;

    try {
      const promptIndex = newKeyPromptIndex !== '' ? parseInt(newKeyPromptIndex) : null;
      const result = await api.createAPIKey(newKeyName.trim(), newKeyStore, promptIndex);
      setCreatedKey(result);
      setNewKeyName('');
      setNewKeyPromptIndex('');
      await loadKeys();
    } catch (e) {
      alert('建立失敗: ' + e.message);
    }
  };

  const handleDelete = async (keyId) => {
    if (!confirm('確定刪除此 API Key？')) return;
    try {
      await api.deleteAPIKey(keyId);
      await loadKeys();
    } catch (e) {
      alert('刪除失敗: ' + e.message);
    }
  };

  const copyToClipboard = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      console.error('Failed to copy:', e);
    }
  };

  const generateCurl = (apiKey) => {
    const baseUrl = window.location.origin;
    return `curl -X POST ${baseUrl}/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${apiKey}" \\
  -d '{
    "model": "gemini-2.5-flash",
    "messages": [
      {"role": "user", "content": "你好"}
    ]
  }'`;
  };

  const copyCurl = async () => {
    if (!createdKey) return;
    try {
      await navigator.clipboard.writeText(generateCurl(createdKey.key));
      setCopiedCurl(true);
      setTimeout(() => setCopiedCurl(false), 2000);
    } catch (e) {
      console.error('Failed to copy:', e);
    }
  };

  const getStoreDisplayName = (storeName) => {
    const store = stores.find(s => s.name === storeName);
    return store?.display_name || storeName.split('/').pop();
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content modal-large" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>API Key 管理</h2>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>

        <div className="modal-body">
          {/* 建立新 Key */}
          <div className="section">
            <h3>建立新 API Key</h3>
            <form onSubmit={handleCreate} className="create-key-form">
              <input
                type="text"
                placeholder="用途說明 (例: Cursor)"
                value={newKeyName}
                onChange={e => setNewKeyName(e.target.value)}
                className="flex-1"
              />
              <select
                value={newKeyStore}
                onChange={e => setNewKeyStore(e.target.value)}
                required
              >
                <option value="">選擇知識庫</option>
                {stores.map(store => (
                  <option key={store.name} value={store.name}>
                    {store.display_name}
                  </option>
                ))}
              </select>
              <input
                type="number"
                placeholder="Prompt #"
                value={newKeyPromptIndex}
                onChange={e => setNewKeyPromptIndex(e.target.value)}
                min="0"
                max="2"
                style={{ width: '80px' }}
                title="指定 Prompt 索引 (0, 1, 2)，留空使用預設"
              />
              <button type="submit" disabled={!newKeyName.trim() || !newKeyStore}>
                建立
              </button>
            </form>
          </div>

          {/* 顯示剛建立的 Key */}
          {createdKey && (
            <div className="section created-key-section">
              <h3>新 API Key 已建立</h3>
              <div className="created-key-box">
                <code>{createdKey.key}</code>
                <button
                  className="secondary"
                  onClick={() => copyToClipboard(createdKey.key)}
                >
                  {copied ? '已複製!' : '複製'}
                </button>
              </div>
              <p className="warning-text">
                請立即複製並妥善保存，此金鑰只會顯示一次！
              </p>
              <div className="curl-example">
                <div className="curl-header">
                  <span>cURL 範例</span>
                  <button className="secondary small" onClick={copyCurl}>
                    {copiedCurl ? '已複製!' : '複製 cURL'}
                  </button>
                </div>
                <pre>{generateCurl(createdKey.key)}</pre>
              </div>
            </div>
          )}

          {/* Key 列表 */}
          <div className="section">
            <h3>現有 API Keys</h3>
            {loading ? (
              <p>載入中...</p>
            ) : keys.length === 0 ? (
              <p className="empty-text">尚未建立任何 API Key</p>
            ) : (
              <table className="keys-table">
                <thead>
                  <tr>
                    <th>名稱</th>
                    <th>Key</th>
                    <th>知識庫</th>
                    <th>Prompt</th>
                    <th>最後使用</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {keys.map(key => (
                    <tr key={key.id}>
                      <td>{key.name}</td>
                      <td><code>{key.key_prefix}</code></td>
                      <td>{getStoreDisplayName(key.store_name)}</td>
                      <td>{key.prompt_index !== null ? `#${key.prompt_index}` : '預設'}</td>
                      <td>{key.last_used_at ? new Date(key.last_used_at).toLocaleDateString() : '-'}</td>
                      <td>
                        <button
                          className="danger small"
                          onClick={() => handleDelete(key.id)}
                        >
                          刪除
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* 使用說明 */}
          <div className="section">
            <h3>使用方式</h3>
            <div className="curl-example">
              <div className="curl-header">
                <span>cURL 範例</span>
                <button className="secondary small" onClick={() => {
                  navigator.clipboard.writeText(generateCurl('YOUR_API_KEY'));
                  setCopiedCurl(true);
                  setTimeout(() => setCopiedCurl(false), 2000);
                }}>
                  {copiedCurl ? '已複製!' : '複製'}
                </button>
              </div>
              <pre>{generateCurl('YOUR_API_KEY')}</pre>
            </div>
            <p className="usage-note">
              支援模型：gemini-2.5-flash, gemini-2.5-pro, gemini-3-flash-preview, gemini-3-pro-preview
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
