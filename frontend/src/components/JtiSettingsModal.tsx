import { useState, useEffect, useRef } from 'react';
import { X, Upload, FileText, Trash2, Download, Eye, Pencil, Lock, Copy } from 'lucide-react';
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
  language?: string;
}

const SYSTEM_DEFAULT_ID = 'system_default';
const MAX_CUSTOM = 3;

export default function JtiSettingsModal({ isOpen, onClose, onPromptChange, language = 'zh' }: JtiSettingsModalProps) {
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

  // === 知識庫狀態 ===
  interface KBFile { name: string; display_name: string; size?: number; editable?: boolean; }
  const [kbFiles, setKbFiles] = useState<KBFile[]>([]);
  const [kbLoading, setKbLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [confirmDeleteFile, setConfirmDeleteFile] = useState<string | null>(null);
  const [deletingFile, setDeletingFile] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // === 檔案檢視/編輯 ===
  const [viewingFile, setViewingFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>('');
  const [fileEditable, setFileEditable] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [fileEditContent, setFileEditContent] = useState('');
  const [saving, setSaving] = useState(false);
  const [fileLoading, setFileLoading] = useState(false);

  useEffect(() => {
    if (isOpen) {
      loadPrompts();
      if (activeTab === 'kb') loadKbFiles();
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

  // === 知識庫 handlers ===
  const loadKbFiles = async () => {
    setKbLoading(true);
    try {
      const data = await api.listJtiKnowledgeFiles(language);
      setKbFiles(data.files || []);
    } catch (e) {
      console.error('Failed to load KB files:', e);
    } finally {
      setKbLoading(false);
    }
  };

  const handleUploadFiles = async (files: FileList | File[]) => {
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        await api.uploadJtiKnowledgeFile(language, file);
      }
      await loadKbFiles();
      setSuccessMsg(`✅ 已上傳 ${files.length} 個檔案`);
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      alert('上傳失敗: ' + msg);
    } finally {
      setUploading(false);
    }
  };

  const handleDeleteFileClick = (fileName: string) => {
    setConfirmDeleteFile(fileName);
  };

  const handleDeleteFileCancel = () => {
    setConfirmDeleteFile(null);
  };

  const handleDeleteFileConfirm = async () => {
    if (!confirmDeleteFile) return;
    setDeletingFile(true);
    try {
      await api.deleteJtiKnowledgeFile(confirmDeleteFile, language);
      setConfirmDeleteFile(null);
      await loadKbFiles();
      setSuccessMsg('✅ 已刪除檔案');
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      alert('刪除失敗: ' + msg);
    } finally {
      setDeletingFile(false);
    }
  };

  // === 檢視/編輯 handlers ===
  const handleViewFile = async (filename: string) => {
    setViewingFile(filename);
    setFileLoading(true);
    setIsEditing(false);
    try {
      const data = await api.getJtiKnowledgeFileContent(filename, language);
      setFileContent(data.content || '');
      setFileEditable(data.editable || false);
    } catch (e) {
      setFileContent('無法載入檔案內容');
      setFileEditable(false);
    } finally {
      setFileLoading(false);
    }
  };

  const handleDownloadFile = (filename: string) => {
    const url = api.getJtiKnowledgeFileDownloadUrl(filename, language);
    window.open(url, '_blank');
  };

  const handleStartEdit = () => {
    setFileEditContent(fileContent);
    setIsEditing(true);
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
  };

  const handleSaveEdit = async () => {
    if (!viewingFile) return;
    setSaving(true);
    try {
      await api.updateJtiKnowledgeFileContent(viewingFile, fileEditContent, language);
      setFileContent(fileEditContent);
      setIsEditing(false);
      setSuccessMsg('✅ 已儲存變更');
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      alert('儲存失敗: ' + msg);
    } finally {
      setSaving(false);
    }
  };

  const closeViewer = () => {
    setViewingFile(null);
    setFileContent('');
    setIsEditing(false);
  };

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
            className={`jti-settings-tab ${activeTab === 'kb' ? 'active' : ''}`}
            onClick={() => { setActiveTab('kb'); loadKbFiles(); }}
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
                  <div className="jti-success-banner">{successMsg}</div>
                )}
                {/* Prompt list */}
                <div className="jti-prompt-list">
                  {/* === 預設提示詞（唯讀）=== */}
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
                              <span className="jti-prompt-badge custom">自訂</span>
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
            kbLoading ? (
              <div className="jti-settings-loading">載入中...</div>
            ) : (
              <>
                {successMsg && (
                  <div className="jti-success-banner">{successMsg}</div>
                )}

                {/* Upload area */}
                <div
                  className={`jti-kb-upload-zone${dragOver ? ' drag-over' : ''}${uploading ? ' uploading' : ''}`}
                  onClick={() => !uploading && fileInputRef.current?.click()}
                  onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setDragOver(false);
                    if (e.dataTransfer.files.length > 0) handleUploadFiles(e.dataTransfer.files);
                  }}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    hidden
                    onChange={(e) => {
                      if (e.target.files && e.target.files.length > 0) {
                        handleUploadFiles(e.target.files);
                        e.target.value = '';
                      }
                    }}
                  />
                  <Upload size={24} className="jti-kb-upload-icon" />
                  <p className="jti-kb-upload-text">
                    {uploading ? '上傳中...' : '點擊或拖放檔案上傳'}
                  </p>
                  <p className="jti-kb-upload-hint">
                    支援 PDF、TXT、Word 等格式
                  </p>
                </div>

                {/* File list */}
                <div className="jti-kb-file-count">
                  共 {kbFiles.length} 個檔案（{language === 'zh' ? '中文' : 'English'} 知識庫）
                </div>
                {kbFiles.length === 0 ? (
                  <div className="jti-kb-empty">知識庫尚無檔案</div>
                ) : (
                  <div className="jti-kb-file-list">
                    {kbFiles.map((file) => (
                      <div key={file.name} className="jti-kb-file-item">
                        <div
                          className="jti-kb-file-info"
                          onClick={() => handleViewFile(file.name)}
                        >
                          <FileText size={16} className="jti-kb-file-icon" />
                          <span className="jti-kb-file-name">{file.display_name}</span>
                          {file.size && (
                            <span className="jti-kb-file-size">
                              {file.size > 1024 ? `${(file.size / 1024).toFixed(1)}KB` : `${file.size}B`}
                            </span>
                          )}
                        </div>
                        <div className="jti-kb-file-actions">
                          <button
                            className="jti-btn small secondary"
                            onClick={() => handleViewFile(file.name)}
                            title="檢視"
                          >
                            <Eye size={12} />
                          </button>
                          <button
                            className="jti-btn small secondary"
                            onClick={() => handleDownloadFile(file.name)}
                            title="下載"
                          >
                            <Download size={12} />
                          </button>
                          <button
                            className="jti-btn small secondary"
                            onClick={() => handleDeleteFileClick(file.name)}
                            title="刪除"
                          >
                            <Trash2 size={12} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )
          )}
        </div>
      </div>

      {/* Delete confirmation popup */}
      {confirmDeleteId && (
        <div className="jti-confirm-overlay" onClick={handleDeleteCancel}>
          <div className="jti-confirm-box" onClick={e => e.stopPropagation()}>
            <p className="jti-confirm-text">確定要刪除此提示詞嗎？</p>
            <div className="jti-confirm-actions">
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
      {/* Delete file confirmation popup */}
      {confirmDeleteFile && (
        <div className="jti-confirm-overlay" onClick={handleDeleteFileCancel}>
          <div className="jti-confirm-box" onClick={e => e.stopPropagation()}>
            <p className="jti-confirm-text">確定要刪除此檔案嗎？</p>
            <div className="jti-confirm-actions">
              <button
                className="jti-btn small secondary"
                onClick={handleDeleteFileCancel}
                disabled={deletingFile}
              >
                取消
              </button>
              <button
                className="jti-btn small danger"
                onClick={handleDeleteFileConfirm}
                disabled={deletingFile}
              >
                {deletingFile ? '刪除中...' : '確認刪除'}
              </button>
            </div>
          </div>
        </div>
      )}
      {/* File viewer/editor modal */}
      {viewingFile && (
        <div className="jti-viewer-overlay" onClick={closeViewer}>
          <div className="jti-viewer-modal" onClick={e => e.stopPropagation()}>
            {/* Header */}
            <div className="jti-viewer-header">
              <div className="jti-viewer-title">
                <FileText size={16} className="jti-viewer-title-icon" />
                <span className="jti-viewer-title-text">{viewingFile}</span>
              </div>
              <div className="jti-viewer-header-actions">
                <button className="jti-btn small secondary" onClick={() => handleDownloadFile(viewingFile)} title="下載">
                  <Download size={14} />
                </button>
                {fileEditable && !isEditing && (
                  <button className="jti-btn small secondary" onClick={handleStartEdit} title="編輯">
                    <Pencil size={14} />
                  </button>
                )}
                <button className="jti-btn small secondary" onClick={closeViewer}>
                  <X size={14} />
                </button>
              </div>
            </div>

            {/* Content */}
            <div className="jti-viewer-body">
              {fileLoading ? (
                <div className="jti-viewer-loading">載入中...</div>
              ) : isEditing ? (
                <textarea
                  className="jti-viewer-textarea"
                  value={fileEditContent}
                  onChange={e => setFileEditContent(e.target.value)}
                />
              ) : fileContent ? (
                <pre className="jti-viewer-pre">{fileContent}</pre>
              ) : (
                <div className="jti-viewer-empty">
                  此檔案格式不支援線上預覽，請下載查看
                </div>
              )}
            </div>

            {/* Footer - edit actions */}
            {isEditing && (
              <div className="jti-viewer-footer">
                <button className="jti-btn small secondary" onClick={handleCancelEdit} disabled={saving}>
                  取消
                </button>
                <button
                  className="jti-btn small save"
                  onClick={handleSaveEdit}
                  disabled={saving}
                >
                  {saving ? '儲存中...' : '儲存'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
