import { useState } from 'react';
import { Lock, Copy } from 'lucide-react';
import ConfirmDialog from '../ConfirmDialog';

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

export interface JtiPersonaTabProps {
  prompts: Prompt[];
  activePromptId: string | null;
  maxCustom: number;
  loading: boolean;
  successMsg: string | null;
  onSetActive: (promptId: string | null) => Promise<void>;
  onCloneDefault: () => Promise<void>;
  cloning: boolean;
  onCreate: (name: string, content: string) => Promise<void>;
  creating: boolean;
  onStartEdit: (prompt: Prompt) => void;
  editingId: string | null;
  editName: string;
  editContent: string;
  onEditNameChange: (name: string) => void;
  onEditContentChange: (content: string) => void;
  onSaveEdit: () => Promise<void>;
  onCancelEdit: () => void;
  onDeleteClick: (promptId: string) => void;
  confirmDeleteId: string | null;
  deleting: boolean;
  onDeleteConfirm: () => Promise<void>;
  onDeleteCancel: () => void;
}

const SYSTEM_DEFAULT_ID = 'system_default';

export default function JtiPersonaTab({
  prompts,
  activePromptId: _activePromptId,
  maxCustom,
  loading,
  successMsg,
  onSetActive,
  onCloneDefault,
  cloning,
  onCreate,
  creating,
  onStartEdit,
  editingId,
  editName,
  editContent,
  onEditNameChange,
  onEditContentChange,
  onSaveEdit,
  onCancelEdit,
  onDeleteClick,
  confirmDeleteId,
  deleting,
  onDeleteConfirm,
  onDeleteCancel,
}: JtiPersonaTabProps) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [newName, setNewName] = useState('');
  const [newContent, setNewContent] = useState('');

  const customPrompts = prompts.filter(p => p.id !== SYSTEM_DEFAULT_ID);
  const defaultPrompt = prompts.find(p => p.id === SYSTEM_DEFAULT_ID);

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

  const handleCreate = async () => {
    if (!newContent.trim()) return;
    const name = newName.trim() || `自訂人物設定 ${customPrompts.length + 1}`;
    await onCreate(name, newContent.trim());
    setNewName('');
    setNewContent('');
  };

  if (loading) {
    return <div className="jti-settings-loading">載入中...</div>;
  }

  return (
    <>
      {successMsg && (
        <div className="jti-success-banner">{successMsg}</div>
      )}

      <div className="jti-prompt-list">
        {/* 預設人物設定（唯讀） */}
        {defaultPrompt && (
          <div className={`jti-prompt-card ${defaultPrompt.is_active ? 'active' : ''}`}>
            <div className="jti-prompt-card-header">
              <div className="jti-prompt-name-row">
                <Lock size={14} className="jti-prompt-lock-icon" />
                <span className="jti-prompt-name">{defaultPrompt.name}</span>
                <span className="jti-prompt-badge">預設</span>
                <span className="jti-prompt-badge readonly">唯讀</span>
                {defaultPrompt.is_active && (
                  <span className="jti-prompt-active-badge">使用中</span>
                )}
              </div>
              <div className="jti-prompt-actions">
                {!defaultPrompt.is_active && (
                  <button
                    className="jti-btn small primary"
                    onClick={() => onSetActive(null)}
                  >
                    啟用
                  </button>
                )}
                {customPrompts.length < maxCustom && (
                  <button
                    className="jti-btn small secondary"
                    onClick={onCloneDefault}
                    disabled={cloning}
                    title="複製預設內容到新的自訂人物設定"
                  >
                    <Copy size={12} className="jti-prompt-clone-icon" />
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

        {/* 自訂人物設定（可編輯） */}
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
                  onChange={e => onEditNameChange(e.target.value)}
                  placeholder="名稱"
                />
                <textarea
                  className="jti-prompt-textarea"
                  value={editContent}
                  onChange={e => onEditContentChange(e.target.value)}
                  placeholder="人物設定內容..."
                  rows={10}
                />
                <div className="jti-prompt-edit-actions">
                  <button className="jti-btn primary" onClick={onSaveEdit}>
                    儲存
                  </button>
                  <button className="jti-btn secondary" onClick={onCancelEdit}>
                    取消
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="jti-prompt-card-header">
                  <div className="jti-prompt-name-row">
                    <span className="jti-prompt-name">{prompt.name}</span>
                    <span className="jti-prompt-badge custom">自訂</span>
                    {prompt.is_active && (
                      <span className="jti-prompt-active-badge">啟用中</span>
                    )}
                  </div>
                  <div className="jti-prompt-actions">
                    {!prompt.is_active ? (
                      <button
                        className="jti-btn small primary"
                        onClick={() => onSetActive(prompt.id)}
                      >
                        啟用
                      </button>
                    ) : (
                      <button
                        className="jti-btn small secondary"
                        onClick={() => onSetActive(null)}
                      >
                        取消啟用
                      </button>
                    )}
                    <button
                      className="jti-btn small secondary"
                      onClick={() => onStartEdit(prompt)}
                    >
                      編輯
                    </button>
                    <button
                      className="jti-btn small secondary"
                      onClick={() => onDeleteClick(prompt.id)}
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

      {/* Create new persona */}
      {customPrompts.length < maxCustom ? (
        <div className="jti-prompt-create">
          <h3 className="jti-prompt-create-title">
            新增自訂人物設定（{customPrompts.length}/{maxCustom}）
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
            placeholder="人物設定內容..."
            rows={6}
          />
          <button
            className="jti-btn primary full-width"
            onClick={handleCreate}
            disabled={creating || !newContent.trim()}
          >
            {creating ? '建立中...' : '建立人物設定'}
          </button>
        </div>
      ) : (
        <div className="jti-prompt-limit">
          自訂人物設定已達上限（{maxCustom} 個）
        </div>
      )}

      <ConfirmDialog
        isOpen={!!confirmDeleteId}
        message="確定要刪除此人物設定嗎？"
        onConfirm={onDeleteConfirm}
        onCancel={onDeleteCancel}
        loading={deleting}
      />
    </>
  );
}
