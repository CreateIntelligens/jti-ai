interface Prompt {
  id: string;
  name: string;
  content: string;
  created_at: string;
  updated_at: string;
}

export interface PromptTabProps {
  currentStore: string | null;
  prompts: Prompt[];
  activePromptId: string | null;
  maxPrompts: number;
  loading: boolean;
  editingId: string | null;
  editName: string;
  editContent: string;
  expandedIds: Set<string>;
  newPromptName: string;
  newPromptContent: string;
  creating: boolean;
  onCreatePrompt: () => void;
  onSetActive: (promptId: string | null) => void;
  onDelete: (promptId: string) => void;
  onStartEdit: (prompt: Prompt) => void;
  onCancelEdit: () => void;
  onSaveEdit: () => void;
  onToggleExpand: (promptId: string) => void;
  onNewPromptNameChange: (v: string) => void;
  onNewPromptContentChange: (v: string) => void;
  onEditNameChange: (v: string) => void;
  onEditContentChange: (v: string) => void;
}

function getPreviewText(content: string, maxLines = 3): string {
  const lines = content.split('\n');
  if (lines.length <= maxLines) return content;
  return lines.slice(0, maxLines).join('\n') + '...';
}

export default function PromptTab({
  currentStore,
  prompts,
  activePromptId,
  maxPrompts,
  loading,
  editingId,
  editName,
  editContent,
  expandedIds,
  newPromptName,
  newPromptContent,
  creating,
  onCreatePrompt,
  onSetActive,
  onDelete,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  onToggleExpand,
  onNewPromptNameChange,
  onNewPromptContentChange,
  onEditNameChange,
  onEditContentChange,
}: PromptTabProps) {
  if (!currentStore) {
    return (
      <p style={{ color: '#8090b0', textAlign: 'center', padding: '2rem 0' }}>
        請先選擇知識庫
      </p>
    );
  }

  if (loading) {
    return (
      <p style={{ color: 'var(--crystal-amber)', textAlign: 'center', padding: '2rem 0' }}>
        載入中...
      </p>
    );
  }

  return (
    <div className="modal-content">
      <div>
        <h3 style={{ fontSize: '1.1rem', marginBottom: '1rem', color: 'var(--crystal-cyan)' }}>
          建立新 Prompt {prompts.length >= maxPrompts && <span style={{ color: 'var(--crystal-amber)' }}>（已達上限 {maxPrompts} 個）</span>}
        </h3>
        {prompts.length < maxPrompts && (
          <>
            <input
              type="text"
              value={newPromptName}
              onChange={e => onNewPromptNameChange(e.target.value)}
              placeholder="Prompt 名稱（可選，預設自動命名）"
              style={{ width: '100%', marginBottom: '0.5rem' }}
            />
            <textarea
              value={newPromptContent}
              onChange={e => onNewPromptContentChange(e.target.value)}
              placeholder="Prompt 內容..."
              style={{ minHeight: '150px', width: '100%', marginBottom: '0.5rem', resize: 'vertical' }}
            />
            <button
              onClick={onCreatePrompt}
              disabled={creating || !newPromptContent.trim()}
              style={{ width: '100%' }}
            >
              {creating ? '建立中...' : '✓ 建立 Prompt'}
            </button>
          </>
        )}
      </div>

      <div>
        <h3 style={{ fontSize: '1.1rem', marginBottom: '1rem', color: 'var(--crystal-amber)' }}>
          現有 Prompts
        </h3>
        {prompts.length === 0 ? (
          <p style={{ color: '#8090b0', textAlign: 'center', padding: '2rem 0' }}>
            尚無 Prompt
          </p>
        ) : (
          <ul className="file-list">
            {prompts.map(prompt => (
              <li key={prompt.id} style={{ flexDirection: 'column', alignItems: 'stretch', gap: '0.5rem' }}>
                {editingId === prompt.id ? (
                  <>
                    <input
                      type="text"
                      value={editName}
                      onChange={e => onEditNameChange(e.target.value)}
                      style={{ width: '100%' }}
                    />
                    <textarea
                      value={editContent}
                      onChange={e => onEditContentChange(e.target.value)}
                      style={{ minHeight: '300px', maxHeight: '500px', width: '100%', resize: 'vertical' }}
                    />
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <button onClick={onSaveEdit} className="small">✓ 儲存</button>
                      <button onClick={onCancelEdit} className="secondary small">✕ 取消</button>
                    </div>
                  </>
                ) : (
                  <>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <strong>{prompt.name}</strong>
                        {prompt.id === activePromptId && (
                          <span style={{ marginLeft: '0.5rem', color: 'var(--crystal-teal)' }}>◆ 啟用中</span>
                        )}
                      </div>
                      <div style={{ display: 'flex', gap: '0.5rem' }}>
                        {prompt.id !== activePromptId ? (
                          <button onClick={() => onSetActive(prompt.id)} className="small">
                            ◆ 啟用
                          </button>
                        ) : (
                          <button onClick={() => onSetActive(null)} className="secondary small">
                            ○ 取消啟用
                          </button>
                        )}
                        <button onClick={() => onStartEdit(prompt)} className="secondary small">
                          ✎ 編輯
                        </button>
                        <button onClick={() => onDelete(prompt.id)} className="danger small">
                          ✕ 刪除
                        </button>
                      </div>
                    </div>
                    <div style={{ position: 'relative' }}>
                      <pre style={{
                        fontSize: '0.85rem',
                        color: '#8090b0',
                        whiteSpace: 'pre-wrap',
                        background: 'rgba(0,0,0,0.2)',
                        padding: '0.5rem',
                        borderRadius: '4px',
                        margin: 0,
                        maxHeight: expandedIds.has(prompt.id) ? '400px' : 'none',
                        overflow: expandedIds.has(prompt.id) ? 'auto' : 'visible',
                        transition: 'max-height 0.3s ease'
                      }}>
                        {expandedIds.has(prompt.id) ? prompt.content : getPreviewText(prompt.content)}
                      </pre>
                      {prompt.content.split('\n').length > 3 && (
                        <button
                          onClick={() => onToggleExpand(prompt.id)}
                          className="secondary small"
                          style={{
                            marginTop: '0.5rem',
                            fontSize: '0.8rem',
                            padding: '0.25rem 0.75rem'
                          }}
                        >
                          {expandedIds.has(prompt.id) ? '▲ 收起' : '▼ 展開完整內容'}
                        </button>
                      )}
                    </div>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
