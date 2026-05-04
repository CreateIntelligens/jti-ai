import { useState, useEffect } from 'react';
import { KeyRound, Users, X } from 'lucide-react';
import * as api from '../services/api';
import { useEscapeKey } from '../hooks/useEscapeKey';

interface ApiKeysPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onApiKeySaved: () => void;
}

export default function ApiKeysPanel({ isOpen, onClose, onApiKeySaved }: ApiKeysPanelProps) {
  const [keys, setKeys] = useState<{ name: string; key: string }[]>([]);
  const [activeKey, setActiveKey] = useState('system');
  const [newName, setNewName] = useState('');
  const [newKey, setNewKey] = useState('');
  const [saving, setSaving] = useState(false);

  useEscapeKey(onClose, isOpen);

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

  if (!isOpen) return null;

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

  const maskKey = (key: string) => {
    if (key.length <= 8) return '••••••••';
    return key.slice(0, 4) + '••••' + key.slice(-4);
  };

  return (
    <div className="rp-overlay" onClick={onClose}>
      <div className="rp-panel" onClick={(e) => e.stopPropagation()}>
        <div className="rp-header">
          <span className="rp-title">API Key 管理</span>
          <button className="icon-btn" onClick={onClose}><X size={18} /></button>
        </div>
        <div className="rp-body">
          {/* System key selector */}
          <div>
            <div className="rp-section-title">使用中的 Key</div>
            <div className="rp-stack">
              {/* System default */}
              <div
                className="key-card"
                style={{ cursor: 'pointer', borderColor: activeKey === 'system' ? 'var(--primary)' : undefined }}
                onClick={() => handleSelect('system')}
              >
                <div className="kc-icon kc-icon-system">
                  <KeyRound className="kc-icon-glyph-system" size={16} />
                </div>
                <div className="kc-info">
                  <div className="kc-name-row">
                    <span className="kc-name">系統預設</span>
                    <span className="kc-badge system">系統</span>
                  </div>
                  <div className="kc-meta">使用伺服器端 Gemini Key</div>
                </div>
                {activeKey === 'system' && (
                  <span className="kc-active-tag">✓ 使用中</span>
                )}
              </div>

              {/* User keys */}
              {keys.map((k) => (
                <div
                  key={k.name}
                  className="key-card"
                  style={{ cursor: 'pointer', borderColor: activeKey === k.name ? 'var(--primary)' : undefined }}
                  onClick={() => handleSelect(k.name)}
                >
                  <div className="kc-icon kc-icon-user">
                    <Users className="kc-icon-glyph-user" size={16} />
                  </div>
                  <div className="kc-info">
                    <div className="kc-name-row">
                      <span className="kc-name">{k.name}</span>
                      <span className="kc-badge user">用戶</span>
                    </div>
                    <div className="kc-meta">{maskKey(k.key)}</div>
                  </div>
                  <button className="btn btn-danger btn-sm shrink-0" onClick={(e) => { e.stopPropagation(); handleDelete(k.name); }} >
                    刪除
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div className="sep-row"><div className="sep-line" /></div>

          {/* Add new key */}
          <div>
            <div className="rp-section-title">新增 Gemini Key</div>
            <div className="rp-form-stack">
              <div className="inline-row">
                <input className="input-base flex-1" placeholder="名稱" value={newName} onChange={(e) => setNewName(e.target.value)} />
                <input className="input-base flex-2" type="password" placeholder="Gemini API Key（例如 AIza...）" value={newKey} onChange={(e) => setNewKey(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleSave()} />
              </div>
              <button className="btn btn-primary btn-sm self-start" onClick={handleSave} disabled={!newName.trim() || !newKey.trim() || saving} >
                {saving ? '儲存中...' : '新增'}
              </button>
            </div>
            <div className="rp-info-box">
              Key 僅存於瀏覽器，不會上傳。首頁的一般知識庫與聊天會使用你選取的 Gemini Key。
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
