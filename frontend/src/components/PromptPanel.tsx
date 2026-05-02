import { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import * as api from '../services/api';
import { useEscapeKey } from '../hooks/useEscapeKey';

interface PromptPanelProps {
  isOpen: boolean;
  onClose: () => void;
  currentStore: string | null;
  currentStoreName?: string | null;
  onRestartChat: () => void | Promise<void>;
  onShowStatus?: (msg: string) => void;
}

interface Prompt {
  id: string;
  name: string;
  content: string;
}

export default function PromptPanel({
  isOpen,
  onClose,
  currentStore,
  currentStoreName,
  onRestartChat,
  onShowStatus,
}: PromptPanelProps) {
  const [promptTab, setPromptTab] = useState<'system' | 'rag' | 'model'>('system');

  // Prompt state
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [activePromptId, setActivePromptId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [newPromptName, setNewPromptName] = useState('');
  const [newPromptContent, setNewPromptContent] = useState('');
  const [creating, setCreating] = useState(false);
  const [maxPrompts, setMaxPrompts] = useState(3);

  // Model state
  const [selectedModel, setSelectedModel] = useState(() =>
    localStorage.getItem('selectedModel') || 'gemini-2.5-flash-lite',
  );

  useEscapeKey(onClose, isOpen);

  useEffect(() => {
    if (isOpen && currentStore) loadPrompts();
  }, [isOpen, currentStore]);

  const loadPrompts = async () => {
    if (!currentStore) return;
    setLoading(true);
    try {
      const data = await api.listPrompts(currentStore);
      setPrompts(data.prompts || []);
      setActivePromptId(data.active_prompt_id);
      setMaxPrompts(data.max_prompts || 3);
    } catch (e) {
      console.error('Failed to load prompts:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!currentStore || !newPromptContent.trim()) return;
    setCreating(true);
    try {
      const name = newPromptName.trim() || `Prompt ${prompts.length + 1}`;
      await api.createPrompt(currentStore, name, newPromptContent.trim());
      setNewPromptName('');
      setNewPromptContent('');
      await loadPrompts();
      onShowStatus?.('✅ Prompt 已建立');
    } catch (e) {
      alert('建立失敗: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setCreating(false);
    }
  };

  const handleSetActive = async (promptId: string | null) => {
    if (!currentStore) return;
    try {
      await api.setActivePrompt(currentStore, promptId);
      await loadPrompts();
      await onRestartChat();
      onShowStatus?.('✅ Prompt 已套用');
    } catch (e) {
      alert('設定失敗: ' + (e instanceof Error ? e.message : String(e)));
    }
  };

  const handleDelete = async (promptId: string) => {
    if (!currentStore || !confirm('確定要刪除此 Prompt 嗎？')) return;
    try {
      await api.deletePrompt(currentStore, promptId);
      await loadPrompts();
      if (promptId === activePromptId) await onRestartChat();
    } catch (e) {
      alert('刪除失敗: ' + (e instanceof Error ? e.message : String(e)));
    }
  };

  const handleModelChange = async (modelId: string) => {
    setSelectedModel(modelId);
    localStorage.setItem('selectedModel', modelId);
    await onRestartChat();
    onShowStatus?.('✅ 模型已切換');
  };

  if (!isOpen) return null;

  return (
    <div className="rp-overlay" onClick={onClose}>
      <div className="rp-panel" onClick={(e) => e.stopPropagation()}>
        <div className="rp-header">
          <span className="rp-title">Prompt 設定</span>
          <button className="icon-btn" onClick={onClose}><X size={18} /></button>
        </div>
        <div className="rp-body">
          {!currentStore ? (
            <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-3)', fontSize: '.875rem' }}>
              請先在左側選擇一個知識庫
            </div>
          ) : (
            <>
              <div style={{ fontSize: '.875rem', color: 'var(--text-2)', fontWeight: 600 }}>
                目前知識庫：{currentStoreName || currentStore}
              </div>

              <div className="prompt-tab-row">
                {([['system', '系統 Prompt'], ['rag', 'RAG 指引'], ['model', '模型設定']] as const).map(
                  ([id, label]) => (
                    <button
                      key={id}
                      className={`prompt-tab${promptTab === id ? ' active' : ''}`}
                      onClick={() => setPromptTab(id)}
                    >
                      {label}
                    </button>
                  ),
                )}
              </div>

              {promptTab === 'system' && (
                <div>
                  {/* Existing prompts */}
                  {loading ? (
                    <div style={{ color: 'var(--text-3)', fontSize: '.875rem' }}>載入中...</div>
                  ) : (
                    <>
                      {prompts.length > 0 && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '.5rem', marginBottom: '1rem' }}>
                          {prompts.map((p) => (
                            <div key={p.id} className="key-card" style={{ cursor: 'pointer' }} onClick={() => handleSetActive(p.id)}>
                              <div className="kc-info" style={{ flex: 1 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '.375rem' }}>
                                  <span className="kc-name">{p.name}</span>
                                  {p.id === activePromptId && <span className="kc-badge system">使用中</span>}
                                </div>
                                <div className="kc-meta" style={{ whiteSpace: 'pre-wrap', marginTop: '.25rem' }}>
                                  {p.content.length > 80 ? p.content.slice(0, 80) + '...' : p.content}
                                </div>
                              </div>
                              <button
                                className="btn btn-danger btn-sm"
                                onClick={(e) => { e.stopPropagation(); handleDelete(p.id); }}
                                style={{ flexShrink: 0 }}
                              >
                                刪除
                              </button>
                            </div>
                          ))}
                          {activePromptId && (
                            <button
                              className="btn btn-ghost btn-sm"
                              style={{ alignSelf: 'flex-start' }}
                              onClick={() => handleSetActive(null)}
                            >
                              取消使用 Prompt
                            </button>
                          )}
                        </div>
                      )}

                      {/* Create new */}
                      {prompts.length < maxPrompts && (
                        <div className="field">
                          <label>新增 Prompt</label>
                          <input
                            className="input-base"
                            placeholder="Prompt 名稱（可留空）"
                            value={newPromptName}
                            onChange={(e) => setNewPromptName(e.target.value)}
                          />
                          <textarea
                            className="textarea-base"
                            placeholder="系統角色提示內容..."
                            value={newPromptContent}
                            onChange={(e) => setNewPromptContent(e.target.value)}
                          />
                          <button
                            className="btn btn-primary btn-sm"
                            style={{ alignSelf: 'flex-start' }}
                            onClick={handleCreate}
                            disabled={creating || !newPromptContent.trim()}
                          >
                            {creating ? '建立中...' : '建立'}
                          </button>
                          <span className="field-hint">套用後將在下次對話生效。最多 {maxPrompts} 個。</span>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}

              {promptTab === 'rag' && (
                <div className="field">
                  <label>RAG 檢索指引</label>
                  <textarea
                    className="textarea-base"
                    defaultValue={'優先從近期上傳的文件中檢索。\n若找不到相關資訊，請明確告知使用者。\n最多引用 3 個來源文件。'}
                  />
                  <span className="field-hint">控制 RAG 檢索行為與回答格式。（此功能規劃中）</span>
                </div>
              )}

              {promptTab === 'model' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  <div className="field">
                    <label>模型</label>
                    <select
                      className="input-base"
                      value={selectedModel}
                      onChange={(e) => handleModelChange(e.target.value)}
                    >
                      <option value="gemini-2.5-flash-lite">gemini-2.5-flash-lite</option>
                      <option value="gemini-2.0-flash">gemini-2.0-flash</option>
                      <option value="gemini-2.5-flash">gemini-2.5-flash</option>
                      <option value="gemini-2.5-pro">gemini-2.5-pro</option>
                      <option value="gemini-3.1-flash-lite-preview">gemini-3.1-flash-lite (preview)</option>
                    </select>
                  </div>
                  <div className="field">
                    <label>Temperature</label>
                    <input className="input-base" type="range" min="0" max="1" step="0.1" defaultValue="0.7" />
                    <span className="field-hint">0 = 穩定，1 = 創意。（此功能規劃中）</span>
                  </div>
                  <div className="field">
                    <label>Distance Threshold（RAG）</label>
                    <input className="input-base" type="number" min="0" max="1" step="0.01" defaultValue="0.85" />
                    <span className="field-hint">低於此相似度的文件不會被引用。（此功能規劃中）</span>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
