import { useState, useEffect } from 'react';

// 格式化 Store 顯示名稱（只顯示前8字符ID）
const formatStoreId = (storeName) => {
  if (!storeName) return '未選擇';
  const id = storeName.split('/').pop() || '';
  return id.slice(0, 8);
};

export default function PromptManagementModal({ 
  isOpen, 
  onClose, 
  currentStore,
  onRefresh,
  onRestartChat
}) {
  const [prompts, setPrompts] = useState([]);
  const [activePromptId, setActivePromptId] = useState(null);
  const [maxPrompts, setMaxPrompts] = useState(3);
  const [loading, setLoading] = useState(false);
  const [editingPrompt, setEditingPrompt] = useState(null);
  const [newPrompt, setNewPrompt] = useState({ name: '', content: '' });
  const [showCreateForm, setShowCreateForm] = useState(false);

  // 載入 Prompts
  const loadPrompts = async () => {
    if (!currentStore) return;
    
    setLoading(true);
    try {
      const response = await fetch(`/api/stores/${encodeURIComponent(currentStore)}/prompts`);
      if (!response.ok) throw new Error('載入失敗');
      
      const data = await response.json();
      setPrompts(data.prompts || []);
      setActivePromptId(data.active_prompt_id);
      setMaxPrompts(data.max_prompts || 3);
    } catch (error) {
      alert('載入 Prompts 失敗: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  // 當彈窗打開時載入資料
  useEffect(() => {
    if (isOpen && currentStore) {
      loadPrompts();
    }
  }, [isOpen, currentStore]);

  // 建立新 Prompt
  const handleCreate = async () => {
    // 如果名稱為空，自動產生 "Prompt N"
    const finalName = newPrompt.name.trim() || `Prompt ${prompts.length + 1}`;
    const finalContent = newPrompt.content; // 允許空內容 (不 trim，保留原始輸入)

    try {
      const response = await fetch(`/api/stores/${encodeURIComponent(currentStore)}/prompts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: finalName, content: finalContent })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || '建立失敗');
      }

      setNewPrompt({ name: '', content: '' });
      setShowCreateForm(false);
      await loadPrompts();
    } catch (error) {
      alert(error.message);
    }
  };

  // 更新 Prompt
  const handleUpdate = async (promptId, updates) => {
    try {
      const response = await fetch(`/api/stores/${encodeURIComponent(currentStore)}/prompts/${promptId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates)
      });

      if (!response.ok) throw new Error('更新失敗');

      setEditingPrompt(null);
      await loadPrompts();
    } catch (error) {
      alert('更新失敗: ' + error.message);
    }
  };

  // 刪除 Prompt
  const handleDelete = async (promptId) => {
    if (!confirm('確定要刪除此 Prompt？')) return;

    try {
      const response = await fetch(`/api/stores/${encodeURIComponent(currentStore)}/prompts/${promptId}`, {
        method: 'DELETE'
      });

      if (!response.ok) throw new Error('刪除失敗');

      await loadPrompts();
    } catch (error) {
      alert('刪除失敗: ' + error.message);
    }
  };

  // 設定啟用的 Prompt
  const handleSetActive = async (promptId) => {
    try {
      const response = await fetch(`/api/stores/${encodeURIComponent(currentStore)}/prompts/active`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt_id: promptId })
      });

      if (!response.ok) throw new Error('設定失敗');

      await loadPrompts();
      
      // 自動重新啟動對話以套用 Prompt
      if (onRestartChat) {
        await onRestartChat();
      }
      
      alert('✅ Prompt 已啟用！\n\n已自動重新開始對話，新的對話將套用此 Prompt。');
    } catch (error) {
      alert('設定失敗: ' + error.message);
    }
  };

  if (!isOpen) return null;

  return (
    <div 
      className="modal-overlay" 
      onClick={onClose}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000
      }}
    >
      <div 
        className="modal-content"
        onClick={(e) => e.stopPropagation()}
        style={{
          backgroundColor: 'white',
          borderRadius: '8px',
          padding: '2rem',
          width: '90%',
          maxWidth: '800px',
          maxHeight: '85vh',
          overflow: 'auto',
          boxShadow: '0 4px 20px rgba(0,0,0,0.15)'
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
          <div>
            <h2 style={{ margin: 0, fontSize: '1.5rem' }}>💬 Prompt 管理</h2>
            <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.9rem', color: '#666' }}>
              知識庫 ID: <strong>{formatStoreId(currentStore)}</strong>
            </p>
          </div>
          <button 
            onClick={onClose}
            style={{ 
              background: 'none', 
              border: 'none', 
              fontSize: '1.5rem', 
              cursor: 'pointer',
              color: '#666',
              padding: '0.25rem 0.5rem'
            }}
          >
            ×
          </button>
        </div>

        {!currentStore ? (
          <p style={{ textAlign: 'center', padding: '2rem', color: '#999' }}>
            請先選擇知識庫
          </p>
        ) : loading ? (
          <p style={{ textAlign: 'center', padding: '2rem', color: '#999' }}>
            載入中...
          </p>
        ) : (
          <>
            {/* 統計資訊 */}
            <div style={{ 
              padding: '1rem', 
              backgroundColor: '#f5f5f5', 
              borderRadius: '6px', 
              marginBottom: '1.5rem',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}>
              <span style={{ fontSize: '0.9rem', color: '#666' }}>
                已使用 <strong>{prompts.length}</strong> / {maxPrompts} 個 Prompt
              </span>
              <button
                onClick={() => setShowCreateForm(!showCreateForm)}
                disabled={prompts.length >= maxPrompts}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: prompts.length >= maxPrompts ? '#ccc' : '#4CAF50',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: prompts.length >= maxPrompts ? 'not-allowed' : 'pointer',
                  fontSize: '0.9rem',
                  fontWeight: 500
                }}
              >
                ➕ 新增 Prompt
              </button>
            </div>

            {/* 建立表單 */}
            {showCreateForm && (
              <div style={{ 
                padding: '1.5rem', 
                border: '2px dashed #4CAF50', 
                borderRadius: '8px', 
                marginBottom: '1.5rem',
                backgroundColor: '#f9fff9'
              }}>
                <h3 style={{ margin: '0 0 1rem 0', fontSize: '1.1rem', color: '#4CAF50' }}>
                  新增 Prompt
                </h3>
                <div style={{ marginBottom: '1rem' }}>
                  <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
                    名稱:
                  </label>
                  <input
                    type="text"
                    value={newPrompt.name}
                    onChange={(e) => setNewPrompt({ ...newPrompt, name: e.target.value })}
                    placeholder="例如: 客服助手"
                    style={{
                      width: '100%',
                      padding: '0.75rem',
                      border: '1px solid #ddd',
                      borderRadius: '4px',
                      fontSize: '1rem'
                    }}
                  />
                </div>
                <div style={{ marginBottom: '1rem' }}>
                  <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
                    Prompt 內容:
                  </label>
                  <textarea
                    value={newPrompt.content}
                    onChange={(e) => setNewPrompt({ ...newPrompt, content: e.target.value })}
                    placeholder="你是一個專業的客服人員..."
                    rows={12}
                    style={{
                      width: '100%',
                      padding: '0.75rem',
                      border: '1px solid #ddd',
                      borderRadius: '4px',
                      fontSize: '0.95rem',
                      fontFamily: 'inherit',
                      resize: 'vertical',
                      minHeight: '200px'
                    }}
                  />
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                  <button
                    onClick={() => {
                      setShowCreateForm(false);
                      setNewPrompt({ name: '', content: '' });
                    }}
                    style={{
                      padding: '0.5rem 1rem',
                      backgroundColor: '#f5f5f5',
                      border: '1px solid #ddd',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      fontSize: '0.9rem'
                    }}
                  >
                    取消
                  </button>
                  <button
                    onClick={handleCreate}
                    style={{
                      padding: '0.5rem 1.5rem',
                      backgroundColor: '#4CAF50',
                      color: 'white',
                      border: 'none',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      fontSize: '0.9rem',
                      fontWeight: 500
                    }}
                  >
                    建立
                  </button>
                </div>
              </div>
            )}

            {/* Prompts 列表 */}
            {prompts.length === 0 ? (
              <p style={{ textAlign: 'center', padding: '2rem', color: '#999', fontStyle: 'italic' }}>
                尚無 Prompt，點擊上方按鈕新增
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {prompts.map(prompt => (
                  <div
                    key={prompt.id}
                    style={{
                      padding: '1.5rem',
                      border: activePromptId === prompt.id ? '2px solid #4CAF50' : '1px solid #ddd',
                      borderRadius: '8px',
                      backgroundColor: activePromptId === prompt.id ? '#f9fff9' : '#fff',
                      position: 'relative'
                    }}
                  >
                    {/* 啟用標記 */}
                    {activePromptId === prompt.id && (
                      <div style={{
                        position: 'absolute',
                        top: '1rem',
                        right: '1rem',
                        padding: '0.25rem 0.75rem',
                        backgroundColor: '#4CAF50',
                        color: 'white',
                        borderRadius: '12px',
                        fontSize: '0.75rem',
                        fontWeight: 600
                      }}>
                        ✓ 使用中
                      </div>
                    )}

                    {editingPrompt?.id === prompt.id ? (
                      // 編輯模式
                      <>
                        <input
                          type="text"
                          value={editingPrompt.name}
                          onChange={(e) => setEditingPrompt({ ...editingPrompt, name: e.target.value })}
                          style={{
                            width: '100%',
                            padding: '0.5rem',
                            marginBottom: '0.75rem',
                            border: '1px solid #ddd',
                            borderRadius: '4px',
                            fontSize: '1rem',
                            fontWeight: 500
                          }}
                        />
                        <textarea
                          value={editingPrompt.content}
                          onChange={(e) => setEditingPrompt({ ...editingPrompt, content: e.target.value })}
                          rows={10}
                          style={{
                            width: '100%',
                            padding: '0.75rem',
                            border: '1px solid #ddd',
                            borderRadius: '4px',
                            fontSize: '0.95rem',
                            fontFamily: 'inherit',
                            resize: 'vertical',
                            minHeight: '150px'
                          }}
                        />
                        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                          <button
                            onClick={() => setEditingPrompt(null)}
                            style={{
                              padding: '0.4rem 1rem',
                              backgroundColor: '#f5f5f5',
                              border: '1px solid #ddd',
                              borderRadius: '4px',
                              cursor: 'pointer',
                              fontSize: '0.85rem'
                            }}
                          >
                            取消
                          </button>
                          <button
                            onClick={() => handleUpdate(prompt.id, { 
                              name: editingPrompt.name, 
                              content: editingPrompt.content 
                            })}
                            style={{
                              padding: '0.4rem 1rem',
                              backgroundColor: '#2196F3',
                              color: 'white',
                              border: 'none',
                              borderRadius: '4px',
                              cursor: 'pointer',
                              fontSize: '0.85rem',
                              fontWeight: 500
                            }}
                          >
                            儲存
                          </button>
                        </div>
                      </>
                    ) : (
                      // 顯示模式
                      <>
                        <h3 style={{ margin: '0 0 0.75rem 0', fontSize: '1.1rem', paddingRight: '5rem' }}>
                          {prompt.name}
                        </h3>
                        <p style={{ 
                          margin: '0 0 1rem 0', 
                          color: '#333', 
                          fontSize: '0.95rem',
                          whiteSpace: 'pre-wrap',
                          lineHeight: 1.6,
                          backgroundColor: '#f9f9f9',
                          padding: '1rem',
                          borderRadius: '4px',
                          border: '1px solid #eee',
                          maxHeight: '400px',
                          overflowY: 'auto'
                        }}>
                          {prompt.content}
                        </p>
                        <div style={{ 
                          display: 'flex', 
                          gap: '0.5rem', 
                          justifyContent: 'flex-end',
                          paddingTop: '0.5rem',
                          borderTop: '1px solid #eee'
                        }}>
                          {activePromptId !== prompt.id && (
                            <button
                              onClick={() => handleSetActive(prompt.id)}
                              style={{
                                padding: '0.4rem 1rem',
                                backgroundColor: '#4CAF50',
                                color: 'white',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: 'pointer',
                                fontSize: '0.85rem',
                                fontWeight: 500
                              }}
                            >
                              啟用
                            </button>
                          )}
                          <button
                            onClick={() => setEditingPrompt(prompt)}
                            style={{
                              padding: '0.4rem 1rem',
                              backgroundColor: '#2196F3',
                              color: 'white',
                              border: 'none',
                              borderRadius: '4px',
                              cursor: 'pointer',
                              fontSize: '0.85rem',
                              fontWeight: 500
                            }}
                          >
                            編輯
                          </button>
                          <button
                            onClick={() => handleDelete(prompt.id)}
                            style={{
                              padding: '0.4rem 1rem',
                              backgroundColor: '#f44336',
                              color: 'white',
                              border: 'none',
                              borderRadius: '4px',
                              cursor: 'pointer',
                              fontSize: '0.85rem'
                            }}
                          >
                            刪除
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
