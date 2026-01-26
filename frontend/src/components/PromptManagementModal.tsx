import { useState, useEffect } from 'react';
import * as api from '../services/api';

interface PromptManagementModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentStore: string | null;
  onRefresh: () => void;
  onRestartChat: () => void;
}

export default function PromptManagementModal({
  isOpen,
  onClose,
  currentStore,
  onRefresh,
  onRestartChat,
}: PromptManagementModalProps) {
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (isOpen && currentStore) {
      loadPrompt();
    }
  }, [isOpen, currentStore]);

  const loadPrompt = async () => {
    if (!currentStore) return;
    setLoading(true);
    try {
      const data = await api.getPrompt(currentStore);
      setPrompt(data.prompt || '');
    } catch (e) {
      console.error('Failed to load prompt:', e);
      setPrompt('');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!currentStore) return;
    setSaving(true);
    try {
      await api.savePrompt(currentStore, prompt);
      alert('Prompt 已儲存!');
      onRefresh();
      await onRestartChat();
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
        <h2>⚙ 自訂 Prompt</h2>

        {!currentStore ? (
          <p style={{ color: '#8090b0', textAlign: 'center', padding: '2rem 0' }}>
            請先選擇知識庫
          </p>
        ) : loading ? (
          <p style={{ color: 'var(--crystal-amber)', textAlign: 'center', padding: '2rem 0' }}>
            載入中...
          </p>
        ) : (
          <div className="modal-content">
            <div>
              <label style={{ display: 'block', marginBottom: '0.75rem', color: 'var(--crystal-cyan)' }}>
                知識庫: <strong>{currentStore}</strong>
              </label>
              <textarea
                value={prompt}
                onChange={e => setPrompt(e.target.value)}
                placeholder="輸入自訂 Prompt..."
                style={{ minHeight: '200px', width: '100%' }}
              />
              <p style={{ fontSize: '0.85rem', color: '#8090b0', marginTop: '0.5rem' }}>
                此 Prompt 將在每次對話開始時套用
              </p>
            </div>
          </div>
        )}

        <div className="modal-actions">
          <button onClick={onClose} className="secondary">
            取消
          </button>
          {currentStore && !loading && (
            <button onClick={handleSave} disabled={saving}>
              {saving ? '儲存中...' : '✓ 儲存並重啟對話'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
