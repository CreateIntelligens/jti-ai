import { useEffect, useState } from 'react';
import { KeyRound, Users, X } from 'lucide-react';
import * as api from '../services/api';
import { useEscapeKey } from '../hooks/useEscapeKey';
import { useOverlayPressClose } from '../hooks/useOverlayPressClose';
import { PROJECT_COLORS } from '../utils/storeDisplay';

interface ExtKeysPanelProps {
  isOpen: boolean;
  onClose: () => void;
  isAdmin: boolean;
  onApiKeySaved: () => void;
}

interface SavedGeminiKey {
  name: string;
  key: string;
}

function maskKey(key: string): string {
  if (key.length <= 8) return '••••••••';
  return `${key.slice(0, 4)}••••${key.slice(-4)}`;
}

export default function ExtKeysPanel({
  isOpen,
  onClose,
  isAdmin,
  onApiKeySaved,
}: ExtKeysPanelProps) {
  const [systemKeyNames, setSystemKeyNames] = useState<string[]>([]);
  const [savedKeys, setSavedKeys] = useState<SavedGeminiKey[]>([]);
  const [activeKey, setActiveKey] = useState('system');
  const [newName, setNewName] = useState('');
  const [newKey, setNewKey] = useState('');
  const [saving, setSaving] = useState(false);
  const overlayPressClose = useOverlayPressClose(onClose);

  useEscapeKey(onClose, isOpen);

  const reloadLocalKeys = () => {
    setSavedKeys(api.getSavedApiKeys());
    setActiveKey(api.getActiveApiKeyName());
  };

  useEffect(() => {
    if (!isOpen) return;
    reloadLocalKeys();
    setNewName('');
    setNewKey('');

    let active = true;
    if (isAdmin) {
      void api.getKeyInfos()
        .then((data) => {
          if (active) setSystemKeyNames(data.names || []);
        })
        .catch(() => {
          if (active) setSystemKeyNames([]);
        });
    } else {
      setSystemKeyNames([]);
    }
    return () => { active = false; };
  }, [isAdmin, isOpen]);

  const selectKey = (name: string) => {
    api.setActiveApiKey(name);
    setActiveKey(name);
    onApiKeySaved();
  };

  const handleSave = () => {
    const name = newName.trim();
    const key = newKey.trim();
    if (!name || !key) return;
    setSaving(true);
    try {
      api.saveApiKey(name, key);
      setNewName('');
      setNewKey('');
      reloadLocalKeys();
      onApiKeySaved();
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = (name: string) => {
    if (!confirm(`確定要刪除「${name}」嗎？`)) return;
    api.deleteApiKey(name);
    reloadLocalKeys();
    onApiKeySaved();
  };

  if (!isOpen) return null;

  return (
    <div className="rp-overlay" {...overlayPressClose}>
      <div className="rp-panel" onClick={(event) => event.stopPropagation()}>
        <div className="rp-header">
          <span className="rp-title">對外 API Keys</span>
          <button className="icon-btn" onClick={onClose} aria-label="關閉對外 API Keys">
            <X size={18} />
          </button>
        </div>
        <div className="rp-body">
          <div className="rp-info-box ext-key-intro">
            選擇 General 知識庫連線使用的 Gemini Key。自訂 Key 僅儲存在此瀏覽器。
          </div>

          <div>
            <div className="rp-section-title">系統 Gemini Keys（專案）</div>
            <div className="rp-stack">
              <button
                type="button"
                className={`key-card key-card-clickable${activeKey === 'system' ? ' active' : ''}`}
                onClick={() => selectKey('system')}
              >
                <span className="kc-icon kc-icon-system"><KeyRound size={16} /></span>
                <span className="kc-info">
                  <span className="kc-name-row">
                    <span className="kc-name">系統預設</span>
                    <span className="kc-badge system">系統</span>
                  </span>
                  <span className="kc-meta">使用伺服器端 Gemini Key</span>
                </span>
                {activeKey === 'system' && <span className="kc-active-tag">使用中</span>}
              </button>
              {systemKeyNames.map((name, index) => (
                <div key={`${name}-${index}`} className="key-card">
                  <span
                    className="kc-icon project-key-icon"
                    style={{ color: PROJECT_COLORS[index % PROJECT_COLORS.length] }}
                  >
                    <KeyRound size={16} />
                  </span>
                  <span className="kc-info">
                    <span className="kc-name">{name || `專案 ${index + 1}`}</span>
                    <span className="kc-meta">系統專案 Key</span>
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="sep-row"><div className="sep-line" /></div>

          <div>
            <div className="rp-section-title">瀏覽器 Gemini Keys</div>
            <div className="rp-stack">
              {savedKeys.length === 0 && (
                <div className="rp-list-empty">尚未新增自訂 Key</div>
              )}
              {savedKeys.map((savedKey) => (
                <button
                  type="button"
                  key={savedKey.name}
                  className={`key-card key-card-clickable${activeKey === savedKey.name ? ' active' : ''}`}
                  onClick={() => selectKey(savedKey.name)}
                >
                  <span className="kc-icon kc-icon-user"><Users size={16} /></span>
                  <span className="kc-info">
                    <span className="kc-name-row">
                      <span className="kc-name">{savedKey.name}</span>
                      <span className="kc-badge user">自訂</span>
                    </span>
                    <span className="kc-meta">{maskKey(savedKey.key)}</span>
                  </span>
                  {activeKey === savedKey.name && <span className="kc-active-tag">使用中</span>}
                  <span
                    className="btn btn-danger btn-sm"
                    role="button"
                    tabIndex={0}
                    onClick={(event) => {
                      event.stopPropagation();
                      handleDelete(savedKey.name);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        event.stopPropagation();
                        handleDelete(savedKey.name);
                      }
                    }}
                  >
                    刪除
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className="rp-section-title">新增 Gemini Key</div>
            <div className="rp-form-stack">
              <input
                className="input-base"
                placeholder="名稱"
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
              />
              <input
                className="input-base"
                type="password"
                placeholder="Gemini API Key（例如 AIza…）"
                value={newKey}
                onChange={(event) => setNewKey(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') handleSave();
                }}
              />
              <button
                className="btn btn-primary btn-sm self-start"
                onClick={handleSave}
                disabled={saving || !newName.trim() || !newKey.trim()}
              >
                {saving ? '儲存中…' : '新增 Key'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
