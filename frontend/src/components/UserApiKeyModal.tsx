import { useState, useEffect } from 'react';
import * as api from '../services/api';

interface UserApiKeyModalProps {
  isOpen: boolean;
  onClose: () => void;
  onApiKeySaved: () => void;
}

export default function UserApiKeyModal({ isOpen, onClose, onApiKeySaved }: UserApiKeyModalProps) {
  const [keys, setKeys] = useState<{ name: string; key: string }[]>([]);
  const [activeKey, setActiveKey] = useState('system');
  const [newName, setNewName] = useState('');
  const [newKey, setNewKey] = useState('');
  const [saving, setSaving] = useState(false);

  const reload = () => {
    setKeys(api.getSavedApiKeys());
    setActiveKey(api.getActiveApiKeyName());
  };

  useEffect(() => {
    if (isOpen) {
      reload();
      setNewName('');
      setNewKey('');
    }
  }, [isOpen]);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) onClose();
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [isOpen, onClose]);

  const handleSave = () => {
    if (!newName.trim() || !newKey.trim()) return;
    setSaving(true);
    setTimeout(() => {
      api.saveApiKey(newName.trim(), newKey.trim());
      setNewName('');
      setNewKey('');
      setSaving(false);
      reload();
      onApiKeySaved();
    }, 300);
  };

  const handleDelete = (name: string) => {
    if (!confirm(`確定要刪除「${name}」嗎？`)) return;
    api.deleteApiKey(name);
    reload();
    onApiKeySaved();
  };

  const handleSelect = (name: string) => {
    api.setActiveApiKey(name);
    setActiveKey(name);
    onApiKeySaved();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && newName.trim() && newKey.trim()) {
      handleSave();
    }
  };

  const maskKey = (key: string) => {
    if (key.length <= 8) return '••••••••';
    return key.slice(0, 4) + '••••' + key.slice(-4);
  };

  if (!isOpen) return null;

  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: '680px' }}>
        <h2>◈ API Key 設定</h2>

        <div className="modal-content">

          {/* 切換使用的 Key */}
          <div>
            <label style={{
              display: 'block',
              marginBottom: '0.5rem',
              fontSize: '0.8rem',
              color: 'var(--crystal-amber)',
              fontWeight: 600,
              letterSpacing: '1px',
              textTransform: 'uppercase',
            }}>
              使用中的 Key
            </label>
            <select
              value={activeKey}
              onChange={e => handleSelect(e.target.value)}
              aria-label="選擇 API Key"
            >
              <option value="system">◈ 系統預設</option>
              {keys.map(k => (
                <option key={k.name} value={k.name}>
                  ◇ {k.name}
                </option>
              ))}
            </select>
          </div>

          {/* 已儲存的 Key 列表 */}
          {keys.length > 0 && (
            <div>
              <label style={{
                display: 'block',
                marginBottom: '0.5rem',
                fontSize: '0.8rem',
                color: 'var(--crystal-amber)',
                fontWeight: 600,
                letterSpacing: '1px',
                textTransform: 'uppercase',
              }}>
                已儲存（{keys.length}）
              </label>
              <ul className="file-list">
                {keys.map(k => (
                  <li key={k.name} style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', minWidth: 0 }}>
                      <strong style={{
                        color: k.name === activeKey ? 'var(--crystal-teal)' : '#e0e6ff',
                        whiteSpace: 'nowrap',
                      }}>
                        {k.name}
                      </strong>
                      {k.name === activeKey && (
                        <span style={{
                          fontSize: '0.7rem',
                          color: 'var(--crystal-teal)',
                          background: 'rgba(61, 217, 211, 0.1)',
                          padding: '0.15rem 0.5rem',
                          borderRadius: '6px',
                          whiteSpace: 'nowrap',
                        }}>使用中</span>
                      )}
                      <span style={{
                        fontSize: '0.8rem',
                        color: '#6070a0',
                        fontFamily: "'IBM Plex Mono', monospace",
                      }}>
                        {maskKey(k.key)}
                      </span>
                    </div>
                    <button
                      onClick={() => handleDelete(k.name)}
                      className="danger small"
                      style={{ flexShrink: 0 }}
                    >
                      ✕
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 分隔線 */}
          <div style={{
            height: '1px',
            background: 'linear-gradient(to right, transparent, var(--glass-border), transparent)',
          }} />

          {/* 新增 Key — 同一行：名稱 + Key + 按鈕 */}
          <div>
            <label style={{
              display: 'block',
              marginBottom: '0.5rem',
              fontSize: '0.8rem',
              color: 'var(--crystal-amber)',
              fontWeight: 600,
              letterSpacing: '1px',
              textTransform: 'uppercase',
            }}>
              新增 API Key
            </label>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <input
                type="text"
                value={newName}
                onChange={e => setNewName(e.target.value)}
                placeholder="名稱"
                style={{ width: '140px', flexShrink: 0 }}
              />
              <input
                type="password"
                value={newKey}
                onChange={e => setNewKey(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Gemini API Key"
                style={{ flex: 1 }}
              />
              <button
                onClick={handleSave}
                disabled={!newName.trim() || !newKey.trim() || saving}
                style={{ flexShrink: 0 }}
              >
                {saving ? '◎...' : '◆ 新增'}
              </button>
            </div>
          </div>

          {/* 說明（整合為一條） */}
          <div style={{
            padding: '0.6rem 1rem',
            background: 'rgba(42, 49, 84, 0.3)',
            border: '1px solid rgba(61, 217, 211, 0.1)',
            borderRadius: '10px',
            fontSize: '0.8rem',
            color: '#6070a0',
            lineHeight: 1.6,
          }}>
            Key 僅存於瀏覽器，不會上傳。前往{' '}
            <a
              href="https://aistudio.google.com/apikey"
              target="_blank"
              rel="noopener noreferrer"
              style={{
                color: 'var(--crystal-cyan)',
                textDecoration: 'none',
                borderBottom: '1px solid rgba(91, 233, 255, 0.3)',
              }}
            >
              aistudio.google.com/apikey
            </a>{' '}
            建立免費 Key。
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
