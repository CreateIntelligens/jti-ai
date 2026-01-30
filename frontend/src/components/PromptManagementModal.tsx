import { useState, useEffect } from 'react';
import * as api from '../services/api';
import type { Store } from '../types';

interface Prompt {
  id: string;
  name: string;
  content: string;
  created_at: string;
  updated_at: string;
}

interface APIKey {
  id: string;
  key_prefix: string;
  name: string;
  store_name: string;
  prompt_index: number | null;
  created_at: string;
}

interface PromptItem {
  id: string;
  name: string;
  content: string;
  is_active: boolean;
}

interface PromptManagementModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentStore: string | null;
  onRefresh: () => void;
  onRestartChat: () => void;
  stores: Store[];
}

const MODELS = [
  { id: 'gemini-2.5-flash-lite', name: 'Gemini 2.5 Flash Lite', description: '輕量快速版本' },
  { id: 'gemini-3-flash-preview', name: 'Gemini 3 Flash (Preview)', description: '新一代快速模型' },
  { id: 'gemini-3-pro-preview', name: 'Gemini 3 Pro (Preview)', description: '新一代最強模型' },
];

export default function PromptManagementModal({
  isOpen,
  onClose,
  currentStore,
  onRestartChat,
  stores,
}: Omit<PromptManagementModalProps, 'onRefresh'>) {
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [activePromptId, setActivePromptId] = useState<string | null>(null);
  const [maxPrompts, setMaxPrompts] = useState(3);
  const [loading, setLoading] = useState(false);
  const [newPromptName, setNewPromptName] = useState('');
  const [newPromptContent, setNewPromptContent] = useState('');
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editContent, setEditContent] = useState('');
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [selectedModel, setSelectedModel] = useState(() => {
    return localStorage.getItem('selectedModel') || 'gemini-2.5-flash-lite';
  });
  const [activeTab, setActiveTab] = useState<'model' | 'prompt' | 'apikey'>('model');

  // API Key 狀態
  const [apiKeyStore, setApiKeyStore] = useState('');
  const [apiKeyName, setApiKeyName] = useState('');
  const [apiKeyPromptIndex, setApiKeyPromptIndex] = useState<string>('');
  const [apiKeyPrompts, setApiKeyPrompts] = useState<PromptItem[]>([]);
  const [apiKeys, setApiKeys] = useState<APIKey[]>([]);
  const [apiKeysLoading, setApiKeysLoading] = useState(false);
  const [apiKeyCreating, setApiKeyCreating] = useState(false);
  const [newApiKeyCreated, setNewApiKeyCreated] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen && currentStore) {
      loadPrompts();
    }
    if (!isOpen) {
      setNewApiKeyCreated(null);
    }
  }, [isOpen, currentStore]);

  // API Key: 載入金鑰列表
  useEffect(() => {
    if (isOpen && activeTab === 'apikey') {
      loadApiKeys();
    }
  }, [isOpen, activeTab, apiKeyStore]);

  // API Key: 選擇知識庫後載入該庫的 prompt 列表
  useEffect(() => {
    if (apiKeyStore) {
      api.listPrompts(apiKeyStore).then(data => {
        setApiKeyPrompts(Array.isArray(data.prompts) ? data.prompts : []);
      }).catch(() => setApiKeyPrompts([]));
    } else {
      setApiKeyPrompts([]);
    }
    setApiKeyPromptIndex('');
  }, [apiKeyStore]);

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

  // API Key 函數
  const loadApiKeys = async () => {
    setApiKeysLoading(true);
    try {
      const data = await api.listApiKeys(apiKeyStore || undefined);
      setApiKeys(data);
    } catch (e) {
      console.error('Failed to load API keys:', e);
    } finally {
      setApiKeysLoading(false);
    }
  };

  const handleCreateApiKey = async () => {
    if (!apiKeyStore || !apiKeyName.trim()) return;
    setApiKeyCreating(true);
    try {
      const promptIndex = apiKeyPromptIndex !== '' ? Number(apiKeyPromptIndex) : null;
      const result = await api.createApiKey(apiKeyName.trim(), apiKeyStore, promptIndex);
      setNewApiKeyCreated(result.key);
      setApiKeyName('');
      setApiKeyPromptIndex('');
      await loadApiKeys();
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      alert('建立失敗: ' + errorMsg);
    } finally {
      setApiKeyCreating(false);
    }
  };

  const handleDeleteApiKey = async (keyId: string) => {
    if (!confirm('確定要刪除此 API Key 嗎？')) return;
    try {
      await api.deleteServerApiKey(keyId);
      await loadApiKeys();
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      alert('刪除失敗: ' + errorMsg);
    }
  };

  const getApiKeyPromptLabel = (promptIndex: number | null): string => {
    if (promptIndex == null) return '';
    if (apiKeyPrompts.length > 0 && promptIndex < apiKeyPrompts.length) {
      return apiKeyPrompts[promptIndex].name;
    }
    return `Prompt #${promptIndex}`;
  };

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
      // 如果沒填名稱，自動生成預設名稱
      const name = newPromptName.trim() || `Prompt ${prompts.length + 1}`;
      await api.createPrompt(currentStore, name, newPromptContent.trim());
      setNewPromptName('');
      setNewPromptContent('');
      await loadPrompts();
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      alert('建立失敗: ' + errorMsg);
    } finally {
      setCreating(false);
    }
  };

  const handleSetActive = async (promptId: string) => {
    if (!currentStore) return;
    try {
      await api.setActivePrompt(currentStore, promptId);
      await loadPrompts();
      await onRestartChat();
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      alert('設定失敗: ' + errorMsg);
    }
  };

  const handleDelete = async (promptId: string) => {
    if (!currentStore) return;
    if (!confirm('確定要刪除此 Prompt 嗎？')) return;
    try {
      await api.deletePrompt(currentStore, promptId);
      await loadPrompts();
      if (promptId === activePromptId) {
        await onRestartChat();
      }
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      alert('刪除失敗: ' + errorMsg);
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

  const toggleExpand = (promptId: string) => {
    setExpandedIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(promptId)) {
        newSet.delete(promptId);
      } else {
        newSet.add(promptId);
      }
      return newSet;
    });
  };

  const getPreviewText = (content: string, maxLines: number = 3) => {
    const lines = content.split('\n');
    if (lines.length <= maxLines) return content;
    return lines.slice(0, maxLines).join('\n') + '...';
  };

  const saveEdit = async () => {
    if (!currentStore || !editingId) return;
    try {
      await api.updatePrompt(currentStore, editingId, editName, editContent);
      await loadPrompts();
      if (editingId === activePromptId) {
        await onRestartChat();
      }
      cancelEdit();
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      alert('更新失敗: ' + errorMsg);
    }
  };

  const handleModelChange = (modelId: string) => {
    setSelectedModel(modelId);
    localStorage.setItem('selectedModel', modelId);
    // TODO: 通知後端切換模型
    alert(`已切換到 ${MODELS.find(m => m.id === modelId)?.name}`);
  };

  if (!isOpen) return null;

  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: '700px' }}>
        <h2>⚙ 設置</h2>

        {/* 標籤切換 */}
        <div style={{ 
          display: 'flex', 
          gap: '0.5rem', 
          marginBottom: '1.5rem', 
          padding: '0.25rem',
          background: 'rgba(26, 31, 58, 0.6)',
          borderRadius: '12px',
          border: '1px solid rgba(61, 217, 211, 0.15)'
        }}>
          <button
            onClick={() => setActiveTab('model')}
            type="button"
            style={{
              flex: 1,
              padding: '0.75rem 1rem',
              borderRadius: '8px',
              border: 'none',
              background: activeTab === 'model' 
                ? 'linear-gradient(135deg, rgba(61, 217, 211, 0.25), rgba(91, 233, 255, 0.15))' 
                : 'transparent',
              color: activeTab === 'model' ? '#5be9ff' : '#8090b0',
              fontWeight: activeTab === 'model' ? '600' : '400',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              boxShadow: activeTab === 'model' ? '0 2px 8px rgba(61, 217, 211, 0.2)' : 'none'
            }}
          >
            🤖 模型
          </button>
          <button
            onClick={() => setActiveTab('prompt')}
            type="button"
            style={{
              flex: 1,
              padding: '0.75rem 1rem',
              borderRadius: '8px',
              border: 'none',
              background: activeTab === 'prompt' 
                ? 'linear-gradient(135deg, rgba(255, 169, 89, 0.25), rgba(255, 205, 107, 0.15))' 
                : 'transparent',
              color: activeTab === 'prompt' ? '#ffa959' : '#8090b0',
              fontWeight: activeTab === 'prompt' ? '600' : '400',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              boxShadow: activeTab === 'prompt' ? '0 2px 8px rgba(255, 169, 89, 0.2)' : 'none'
            }}
          >
            📝 Prompt
          </button>
          <button
            onClick={() => setActiveTab('apikey')}
            type="button"
            style={{
              flex: 1,
              padding: '0.75rem 1rem',
              borderRadius: '8px',
              border: 'none',
              background: activeTab === 'apikey' 
                ? 'linear-gradient(135deg, rgba(77, 169, 255, 0.25), rgba(91, 233, 255, 0.15))' 
                : 'transparent',
              color: activeTab === 'apikey' ? '#4da9ff' : '#8090b0',
              fontWeight: activeTab === 'apikey' ? '600' : '400',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              boxShadow: activeTab === 'apikey' ? '0 2px 8px rgba(77, 169, 255, 0.2)' : 'none'
            }}
          >
            🔑 API 金鑰
          </button>
        </div>

        {/* 模型選擇頁面 */}
        {activeTab === 'model' && (
          <div className="modal-content">
            <h3 style={{ fontSize: '1.1rem', marginBottom: '1rem', color: 'var(--crystal-cyan)' }}>
              選擇 Gemini 模型
            </h3>
            <p style={{ color: '#8090b0', fontSize: '0.9rem', marginBottom: '1rem' }}>
              選擇用於處理查詢的 AI 模型。不同模型有不同的速度和能力。
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {MODELS.map(model => (
                <div
                  key={model.id}
                  onClick={() => handleModelChange(model.id)}
                  style={{
                    padding: '1rem',
                    border: selectedModel === model.id
                      ? '2px solid var(--crystal-cyan)'
                      : '1px solid rgba(128,144,176,0.3)',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    background: selectedModel === model.id
                      ? 'rgba(64,224,208,0.1)'
                      : 'rgba(0,0,0,0.2)',
                    transition: 'all 0.2s ease'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontWeight: 'bold', color: 'var(--text-primary)', marginBottom: '0.25rem' }}>
                        {model.name}
                        {selectedModel === model.id && (
                          <span style={{ marginLeft: '0.5rem', color: 'var(--crystal-cyan)' }}>✓ 使用中</span>
                        )}
                      </div>
                      <div style={{ fontSize: '0.85rem', color: '#8090b0' }}>{model.description}</div>
                    </div>
                    {selectedModel === model.id && (
                      <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--crystal-cyan)' }} />
                    )}
                  </div>
                </div>
              ))}
            </div>
            <div style={{
              marginTop: '1.5rem',
              padding: '1rem',
              background: 'rgba(64,224,208,0.05)',
              border: '1px solid rgba(64,224,208,0.2)',
              borderRadius: '8px'
            }}>
              <p style={{ fontSize: '0.85rem', color: '#8090b0', margin: 0 }}>
                💡 <strong style={{ color: 'var(--crystal-cyan)' }}>提示：</strong> Flash 模型速度快且免費額度較高，Pro 模型適合需要更深入分析的場景。
              </p>
            </div>
          </div>
        )}

        {/* Prompt 管理頁面 */}
        {activeTab === 'prompt' && (
          !currentStore ? (
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
              <h3 style={{ fontSize: '1.1rem', marginBottom: '1rem', color: 'var(--crystal-cyan)' }}>
                建立新 Prompt {prompts.length >= maxPrompts && <span style={{ color: 'var(--crystal-amber)' }}>（已達上限 {maxPrompts} 個）</span>}
              </h3>
              {prompts.length < maxPrompts && (
                <>
                  <input
                    type="text"
                    value={newPromptName}
                    onChange={e => setNewPromptName(e.target.value)}
                    placeholder="Prompt 名稱（可選，預設自動命名）"
                    style={{ width: '100%', marginBottom: '0.5rem' }}
                  />
                  <textarea
                    value={newPromptContent}
                    onChange={e => setNewPromptContent(e.target.value)}
                    placeholder="Prompt 內容..."
                    style={{ minHeight: '150px', width: '100%', marginBottom: '0.5rem', resize: 'vertical' }}
                  />
                  <button 
                    onClick={handleCreate} 
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
                            onChange={e => setEditName(e.target.value)}
                            style={{ width: '100%' }}
                          />
                          <textarea
                            value={editContent}
                            onChange={e => setEditContent(e.target.value)}
                            style={{ minHeight: '300px', maxHeight: '500px', width: '100%', resize: 'vertical' }}
                          />
                          <div style={{ display: 'flex', gap: '0.5rem' }}>
                            <button onClick={saveEdit} className="small">✓ 儲存</button>
                            <button onClick={cancelEdit} className="secondary small">✕ 取消</button>
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
                              {prompt.id !== activePromptId && (
                                <button onClick={() => handleSetActive(prompt.id)} className="small">
                                  ◆ 啟用
                                </button>
                              )}
                              <button onClick={() => startEdit(prompt)} className="secondary small">
                                ✎ 編輯
                              </button>
                              <button onClick={() => handleDelete(prompt.id)} className="danger small">
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
                                onClick={() => toggleExpand(prompt.id)}
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
          )
        )}

        {/* API 金鑰管理頁面 */}
        {activeTab === 'apikey' && (
          <div className="modal-content">
            {newApiKeyCreated && (
              <div style={{
                padding: '1rem',
                background: 'var(--crystal-amber)',
                color: '#0a0f1a',
                borderRadius: '8px',
                marginBottom: '1rem'
              }}>
                <p style={{ fontWeight: 'bold', marginBottom: '0.5rem' }}>✓ API Key 已建立</p>
                <p style={{ fontSize: '0.9rem', marginBottom: '0.5rem' }}>請妥善保存此金鑰，之後無法再次查看：</p>
                <code style={{
                  display: 'block',
                  padding: '0.5rem',
                  background: 'rgba(0,0,0,0.2)',
                  borderRadius: '4px',
                  wordBreak: 'break-all'
                }}>
                  {newApiKeyCreated}
                </code>
                <button
                  onClick={() => setNewApiKeyCreated(null)}
                  style={{ marginTop: '0.5rem', fontSize: '0.85rem' }}
                >
                  我已保存
                </button>
              </div>
            )}

            <div>
              <h3 style={{ fontSize: '1.1rem', marginBottom: '1rem', color: 'var(--crystal-blue)' }}>
                建立新的 API Key
              </h3>
              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-muted)' }}>
                  選擇知識庫
                </label>
                <select
                  value={apiKeyStore}
                  onChange={e => setApiKeyStore(e.target.value)}
                  className="w-full"
                >
                  <option value="">選擇知識庫...</option>
                  {stores.map(store => (
                    <option key={store.name} value={store.name}>
                      {store.display_name || store.name}
                    </option>
                  ))}
                </select>
              </div>
              {apiKeyStore && (
                <>
                  {apiKeyPrompts.length > 0 && (
                    <div style={{ marginBottom: '1rem' }}>
                      <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-muted)' }}>
                        指定 Prompt（可選）
                      </label>
                      <select
                        value={apiKeyPromptIndex}
                        onChange={e => setApiKeyPromptIndex(e.target.value)}
                        className="w-full"
                      >
                        <option value="">使用預設（啟用中的 Prompt）</option>
                        {apiKeyPrompts.map((p, idx) => (
                          <option key={p.id} value={idx}>
                            {p.name}{p.is_active ? ' (目前啟用)' : ''}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                  <div className="flex gap-md">
                    <input
                      type="text"
                      value={apiKeyName}
                      onChange={e => setApiKeyName(e.target.value)}
                      placeholder="用途說明（例如：測試、生產環境）"
                      className="flex-1"
                      onKeyDown={e => e.key === 'Enter' && handleCreateApiKey()}
                    />
                    <button onClick={handleCreateApiKey} disabled={apiKeyCreating || !apiKeyName.trim()}>
                      {apiKeyCreating ? '建立中...' : '✓ 建立'}
                    </button>
                  </div>
                </>
              )}
            </div>

            <div style={{ marginTop: '1.5rem' }}>
              <h3 style={{ fontSize: '1.1rem', marginBottom: '1rem', color: 'var(--crystal-amber)' }}>
                現有 API Keys
              </h3>
              {apiKeysLoading ? (
                <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem 0' }}>
                  載入中...
                </p>
              ) : apiKeys.length === 0 ? (
                <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem 0' }}>
                  尚無 API Key
                </p>
              ) : (
                <ul className="file-list">
                  {apiKeys.map(key => (
                    <li key={key.id}>
                      <div>
                        <div style={{ fontWeight: 'bold' }}>{key.name}</div>
                        <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                          {key.key_prefix} | {stores.find(s => s.name === key.store_name)?.display_name || key.store_name}
                          {key.prompt_index != null && (
                            <span style={{ color: 'var(--crystal-cyan)', marginLeft: '0.5rem' }}>
                              | {getApiKeyPromptLabel(key.prompt_index)}
                            </span>
                          )}
                        </div>
                      </div>
                      <button
                        onClick={() => handleDeleteApiKey(key.id)}
                        className="danger small"
                      >
                        ✕ 刪除
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}

        <div className="modal-actions">
          <button onClick={onClose} className="secondary">
            關閉
          </button>
        </div>
      </div>
    </div>
  );
}
