import { useState, useEffect } from 'react';
import { X, Lock, Copy } from 'lucide-react';
import * as api from '../services/api';

interface Prompt {
  id: string;
  name: string;
  content: string;
  created_at: string;
  updated_at: string;
  is_default?: boolean;
  readonly?: boolean;
  is_active?: boolean;
}

interface JtiSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onPromptChange: () => void;
}

const SYSTEM_DEFAULT_ID = 'system_default';
const MAX_CUSTOM = 3;

export default function JtiSettingsModal({ isOpen, onClose, onPromptChange }: JtiSettingsModalProps) {
  const [activeTab, setActiveTab] = useState<'prompt' | 'quiz' | 'kb'>('prompt');
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [activePromptId, setActivePromptId] = useState<string | null>(null);
  const [maxCustom, setMaxCustom] = useState(MAX_CUSTOM);
  const [loading, setLoading] = useState(false);

  // 新增表單
  const [newName, setNewName] = useState('');
  const [newContent, setNewContent] = useState('');
  const [creating, setCreating] = useState(false);

  // 編輯（僅用於自訂提示詞）
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editContent, setEditContent] = useState('');

  // 展開
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  // 克隆中
  const [cloning, setCloning] = useState(false);

  // 刪除確認（彈窗）
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  // 成功訊息
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      loadPrompts();
    }
  }, [isOpen]);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        if (editingId) {
          cancelEdit();
        } else {
          onClose();
        }
      }
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [isOpen, onClose, editingId]);

  const loadPrompts = async () => {
    setLoading(true);
    try {
      const data = await api.listJtiPrompts();
      setPrompts(data.prompts || []);
      setActivePromptId(data.active_prompt_id);
      setMaxCustom(data.max_custom_prompts || MAX_CUSTOM);
    } catch (e) {
      console.error('Failed to load JTI prompts:', e);
    } finally {
      setLoading(false);
    }
  };

  const customPrompts = prompts.filter(p => p.id !== SYSTEM_DEFAULT_ID);
  const defaultPrompt = prompts.find(p => p.id === SYSTEM_DEFAULT_ID);

  const handleCreate = async () => {
    if (!newContent.trim()) return;
    setCreating(true);
    try {
      const name = newName.trim() || `自訂提示詞 ${customPrompts.length + 1}`;
      await api.createJtiPrompt(name, newContent.trim());
      setNewName('');
      setNewContent('');
      await loadPrompts();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      alert('建立失敗: ' + msg);
    } finally {
      setCreating(false);
    }
  };

  const handleCloneDefault = async () => {
    setCloning(true);
    try {
      await api.cloneDefaultJtiPrompt();
      await loadPrompts();
      onPromptChange();
      setSuccessMsg('✅ 已複製預設提示詞並啟用');
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      alert('複製失敗: ' + msg);
    } finally {
      setCloning(false);
    }
  };

  const handleSetActive = async (promptId: string | null) => {
    try {
      await api.setActiveJtiPrompt(promptId);
      await loadPrompts();
      onPromptChange();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      alert('設定失敗: ' + msg);
    }
  };

  const handleDeleteClick = (promptId: string) => {
    setConfirmDeleteId(promptId);
  };

  const handleDeleteCancel = () => {
    setConfirmDeleteId(null);
  };

  const handleDeleteConfirm = async () => {
    if (!confirmDeleteId) return;
    const promptId = confirmDeleteId;
    setDeleting(true);
    try {
      await api.deleteJtiPrompt(promptId);
      setConfirmDeleteId(null);
      await loadPrompts();
      if (promptId === activePromptId) {
        onPromptChange();
      }
      setSuccessMsg('✅ 已刪除提示詞');
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      alert('刪除失敗: ' + msg);
    } finally {
      setDeleting(false);
    }
  };

  const startEdit = (prompt: Prompt) => {
    setEditingId(prompt.id);
    setEditName(prompt.name);
    setEditContent(prompt.content);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditName('');
    setEditContent('');
  };

  const saveEdit = async () => {
    if (!editingId) return;
    try {
      await api.updateJtiPrompt(editingId, editName, editContent);
      await loadPrompts();
      if (editingId === activePromptId) {
        onPromptChange();
      }
      cancelEdit();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      alert('更新失敗: ' + msg);
    }
  };

  const toggleExpand = (id: string) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const getPreview = (content: string, maxLines = 3) => {
    const lines = content.split('\n');
    if (lines.length <= maxLines) return content;
    return lines.slice(0, maxLines).join('\n') + '...';
  };

  if (!isOpen) return null;

  return (
    <div className="jti-settings-overlay" onClick={onClose}>
      <div className="jti-settings-modal" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="jti-settings-header">
          <h2 className="jti-settings-title">設定</h2>
          <button className="jti-settings-close" onClick={onClose} aria-label="關閉">
            <X size={20} />
          </button>
        </div>

        {/* Tabs */}
        <div className="jti-settings-tabs">
          <button
            className={`jti-settings-tab ${activeTab === 'prompt' ? 'active' : ''}`}
            onClick={() => setActiveTab('prompt')}
          >
            提示詞
          </button>
          <button
            className={`jti-settings-tab disabled`}
            disabled
            title="即將推出"
          >
            題庫
          </button>
          <button
            className={`jti-settings-tab disabled`}
            disabled
            title="即將推出"
          >
            知識庫
          </button>
        </div>

        {/* Content */}
        <div className="jti-settings-content">
          {activeTab === 'prompt' && (
            loading ? (
              <div className="jti-settings-loading">載入中...</div>
            ) : (
              <>
                {/* Success message */}
                {successMsg && (
                  <div style={{ padding: '0.5rem 0.75rem', marginBottom: '0.75rem', background: 'rgba(61,217,211,0.12)', borderRadius: '0.5rem', color: '#3dd9d3', fontSize: '0.875rem' }}>
                    {successMsg}
                  </div>
                )}
                {/* Prompt list */}
                <div className="jti-prompt-list">
                  {/* === 預設提示詞（唯讀）=== */}
                  {defaultPrompt && (
                    <div className={`jti-prompt-card ${defaultPrompt.is_active ? 'active' : ''}`}>
                      <div className="jti-prompt-card-header">
                        <div className="jti-prompt-name-row">
                          <Lock size={14} style={{ opacity: 0.6, marginRight: '0.25rem' }} />
                          <span className="jti-prompt-name">{defaultPrompt.name}</span>
                          <span className="jti-prompt-badge">預設</span>
                          <span className="jti-prompt-badge" style={{ background: 'rgba(128,144,176,0.2)', color: '#8090b0' }}>唯讀</span>
                          {defaultPrompt.is_active && (
                            <span className="jti-prompt-active-badge">使用中</span>
                          )}
                        </div>
                        <div className="jti-prompt-actions">
                          {!defaultPrompt.is_active && (
                            <button
                              className="jti-btn small primary"
                              onClick={() => handleSetActive(null)}
                            >
                              啟用
                            </button>
                          )}
                          {customPrompts.length < maxCustom && (
                            <button
                              className="jti-btn small secondary"
                              onClick={handleCloneDefault}
                              disabled={cloning}
                              title="複製預設內容到新的自訂提示詞"
                            >
                              <Copy size={12} style={{ marginRight: '0.25rem' }} />
                              {cloning ? '複製中...' : '以此為基礎建立副本'}
                            </button>
                          )}
                        </div>
                      </div>
                      <div className="jti-prompt-preview">
                        <pre className="jti-prompt-content">
                          {expandedIds.has(defaultPrompt.id) ? defaultPrompt.content : getPreview(defaultPrompt.content)}
                        </pre>
                        {defaultPrompt.content.split('\n').length > 3 && (
                          <button
                            className="jti-btn small secondary jti-prompt-expand"
                            onClick={() => toggleExpand(defaultPrompt.id)}
                          >
                            {expandedIds.has(defaultPrompt.id) ? '收起' : '展開完整內容'}
                          </button>
                        )}
                      </div>
                    </div>
                  )}

                  {/* === 自訂提示詞（可編輯）=== */}
                  {customPrompts.map(prompt => (
                    <div
                      key={prompt.id}
                      className={`jti-prompt-card ${prompt.is_active ? 'active' : ''}`}
                    >
                      {editingId === prompt.id ? (
                        <div className="jti-prompt-edit">
                          <input
                            type="text"
                            className="jti-prompt-input"
                            value={editName}
                            onChange={e => setEditName(e.target.value)}
                            placeholder="名稱"
                          />
                          <textarea
                            className="jti-prompt-textarea"
                            value={editContent}
                            onChange={e => setEditContent(e.target.value)}
                            placeholder="提示詞內容..."
                            rows={10}
                          />
                          <div className="jti-prompt-edit-actions">
                            <button className="jti-btn primary" onClick={saveEdit}>
                              儲存
                            </button>
                            <button className="jti-btn secondary" onClick={cancelEdit}>
                              取消
                            </button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <div className="jti-prompt-card-header">
                            <div className="jti-prompt-name-row">
                              <span className="jti-prompt-name">{prompt.name}</span>
                              <span className="jti-prompt-badge" style={{ background: 'rgba(61,217,211,0.15)', color: '#3dd9d3' }}>自訂</span>
                              {prompt.is_active && (
                                <span className="jti-prompt-active-badge">啟用中</span>
                              )}
                            </div>
                            <div className="jti-prompt-actions">
                              {!prompt.is_active ? (
                                <button
                                  className="jti-btn small primary"
                                  onClick={() => handleSetActive(prompt.id)}
                                >
                                  啟用
                                </button>
                              ) : (
                                <button
                                  className="jti-btn small secondary"
                                  onClick={() => handleSetActive(null)}
                                >
                                  取消啟用
                                </button>
                              )}
                              <button
                                className="jti-btn small secondary"
                                onClick={() => startEdit(prompt)}
                              >
                                編輯
                              </button>
                              <button
                                className="jti-btn small secondary"
                                onClick={() => handleDeleteClick(prompt.id)}
                              >
                                刪除
                              </button>
                            </div>
                          </div>
                          <div className="jti-prompt-preview">
                            <pre className="jti-prompt-content">
                              {expandedIds.has(prompt.id) ? prompt.content : getPreview(prompt.content)}
                            </pre>
                            {prompt.content.split('\n').length > 3 && (
                              <button
                                className="jti-btn small secondary jti-prompt-expand"
                                onClick={() => toggleExpand(prompt.id)}
                              >
                                {expandedIds.has(prompt.id) ? '收起' : '展開完整內容'}
                              </button>
                            )}
                          </div>
                        </>
                      )}
                    </div>
                  ))}
                </div>

                {/* Create new prompt */}
                {customPrompts.length < maxCustom ? (
                  <div className="jti-prompt-create">
                    <h3 className="jti-prompt-create-title">
                      新增自訂提示詞（{customPrompts.length}/{maxCustom}）
                    </h3>
                    <input
                      type="text"
                      className="jti-prompt-input"
                      value={newName}
                      onChange={e => setNewName(e.target.value)}
                      placeholder="名稱（可選，預設自動命名）"
                    />
                    <textarea
                      className="jti-prompt-textarea"
                      value={newContent}
                      onChange={e => setNewContent(e.target.value)}
                      placeholder="提示詞內容..."
                      rows={6}
                    />
                    <button
                      className="jti-btn primary full-width"
                      onClick={handleCreate}
                      disabled={creating || !newContent.trim()}
                    >
                      {creating ? '建立中...' : '建立提示詞'}
                    </button>
                  </div>
                ) : (
                  <div className="jti-prompt-limit">
                    自訂提示詞已達上限（{maxCustom} 個）
                  </div>
                )}
              </>
            )
          )}

          {activeTab === 'quiz' && (
            <div className="jti-settings-coming-soon">
              即將推出
            </div>
          )}

          {activeTab === 'kb' && (
            <div className="jti-settings-coming-soon">
              即將推出
            </div>
          )}
        </div>
      </div>

      {/* Delete confirmation popup */}
      {confirmDeleteId && (
        <div
          style={{
            position: 'fixed', inset: 0, zIndex: 10000,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(2px)',
          }}
          onClick={handleDeleteCancel}
        >
          <div
            style={{
              background: '#1e2030', border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: '0.75rem', padding: '1.5rem', maxWidth: '320px',
              textAlign: 'center', boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
            }}
            onClick={e => e.stopPropagation()}
          >
            <p style={{ marginBottom: '1rem', color: '#e0e0e0', fontSize: '0.95rem' }}>
              確定要刪除此提示詞嗎？
            </p>
            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center' }}>
              <button
                className="jti-btn small secondary"
                onClick={handleDeleteCancel}
                disabled={deleting}
              >
                取消
              </button>
              <button
                className="jti-btn small danger"
                onClick={handleDeleteConfirm}
                disabled={deleting}
              >
                {deleting ? '刪除中...' : '確認刪除'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
