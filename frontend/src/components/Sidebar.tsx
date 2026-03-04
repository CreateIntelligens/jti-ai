import { useEffect, useRef, useState } from 'react';
import { Download, Eye, Pencil, X } from 'lucide-react';
import type { FileItem, KnowledgeTarget, CmsAppTarget, KnowledgeLanguage } from '../types';
import CustomSelect from './CustomSelect';
import * as api from '../services/api';

interface SidebarProps {
  isOpen: boolean;
  knowledgeTargets: KnowledgeTarget[];
  currentTargetId: string | null;
  managedContext: {
    appTarget: CmsAppTarget;
    language: KnowledgeLanguage;
  } | null;
  files: FileItem[];
  filesLoading: boolean;
  onTargetChange: (targetId: string) => void;
  onUploadFile: (file: File) => void;
  onDeleteFile: (fileName: string) => void;
  onRefresh: () => void;
  onOpenPromptManagement: () => void;
  onShowStatus?: (message: string) => void;
}

export default function Sidebar({
  isOpen,
  knowledgeTargets,
  currentTargetId,
  managedContext,
  files,
  filesLoading,
  onTargetChange,
  onUploadFile,
  onDeleteFile,
  onRefresh,
  onOpenPromptManagement,
  onShowStatus,
}: SidebarProps) {
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [viewingFile, setViewingFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState('');
  const [fileEditable, setFileEditable] = useState(false);
  const [fileLoading, setFileLoading] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [fileEditContent, setFileEditContent] = useState('');
  const [saving, setSaving] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setViewingFile(null);
    setFileContent('');
    setFileEditable(false);
    setFileLoading(false);
    setIsEditing(false);
    setFileEditContent('');
  }, [currentTargetId]);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = () => {
    setDragOver(false);
  };

  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      await onUploadFile(file);
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (uploading) return;
    const file = e.dataTransfer.files[0];
    if (file) {
      await handleUpload(file);
    }
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      await handleUpload(file);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleViewManagedFile = async (fileName: string) => {
    if (!managedContext) return;
    setViewingFile(fileName);
    setFileLoading(true);
    setIsEditing(false);
    try {
      const data = await api.getManagedKnowledgeFileContent(managedContext.appTarget, fileName, managedContext.language);
      setFileContent(data.content || '');
      setFileEditable(Boolean(data.editable));
    } catch (error) {
      console.error('Failed to load managed file content:', error);
      setFileContent('無法載入檔案內容');
      setFileEditable(false);
    } finally {
      setFileLoading(false);
    }
  };

  const handleDownloadManagedFile = (fileName: string) => {
    if (!managedContext) return;
    api.downloadManagedKnowledgeFile(managedContext.appTarget, fileName, managedContext.language);
  };

  const closeViewer = () => {
    setViewingFile(null);
    setFileContent('');
    setIsEditing(false);
    setFileEditContent('');
  };

  const handleSaveEdit = async () => {
    if (!viewingFile || !managedContext) return;
    setSaving(true);
    try {
      await api.updateManagedKnowledgeFileContent(
        managedContext.appTarget,
        viewingFile,
        fileEditContent,
        managedContext.language,
      );
      setFileContent(fileEditContent);
      setIsEditing(false);
      onShowStatus?.(`已更新 ${managedContext.appTarget.toUpperCase()} 文件`);
      onRefresh();
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error);
      alert('儲存失敗: ' + errorMsg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <aside className={isOpen ? '' : 'closed'} aria-label="側邊欄">
      <div className="sidebar-section fixed-section">
        <h2>知識庫</h2>
        <CustomSelect
          value={currentTargetId || ''}
          onChange={onTargetChange}
          options={knowledgeTargets.length === 0 ? [{ value: '', label: '尚無知識庫' }] : knowledgeTargets.map((target) => ({
            value: target.id,
            label: target.label,
          }))}
          className="w-full"
        />
        <button
          onClick={onRefresh}
          className="secondary w-full mt-sm"
          aria-label="重新整理知識庫"
        >
          ⟳ 重新整理
        </button>
      </div>

      <div className="sidebar-section scrollable-section">
        <h2>文件</h2>

        <div
          className={`drop-zone ${dragOver ? 'dragover' : ''} ${uploading ? 'uploading' : ''}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          role="button"
          tabIndex={0}
          aria-label="上傳文件區域"
        >
          <p>
            {uploading ? '上傳中...' : (
              <>
                拖曳文件至此或 <span className="browse-link">瀏覽</span>
              </>
            )}
          </p>
          <input
            ref={fileInputRef}
            type="file"
            onChange={handleFileSelect}
            style={{ display: 'none' }}
            aria-label="選擇文件"
          />
        </div>

        <div className="file-list-container">
          {filesLoading ? (
            <ul className="file-list" aria-label="載入中">
              {[1, 2, 3].map((i) => (
                <li key={i} className="file-skeleton">
                  <div className="skeleton-bar" style={{ width: `${50 + i * 12}%` }} />
                </li>
              ))}
            </ul>
          ) : files.length > 0 ? (
            <ul className="file-list" aria-label="文件列表">
              {files.map((file, i) => (
                <li key={file.name} className="file-item-enter" style={{ animationDelay: `${i * 40}ms` }}>
                  <span
                    style={{
                      flex: 1,
                      cursor: managedContext ? 'pointer' : 'default',
                      textDecoration: managedContext ? 'underline' : 'none',
                      textUnderlineOffset: managedContext ? '2px' : '0',
                    }}
                    onClick={() => {
                      if (managedContext) {
                        void handleViewManagedFile(file.name);
                      }
                    }}
                  >
                    {file.display_name || file.name}
                  </span>
                  {managedContext ? (
                    <div style={{ display: 'flex', gap: '0.25rem' }}>
                      <button
                        onClick={() => void handleViewManagedFile(file.name)}
                        className="secondary small"
                        aria-label={`查看文件 ${file.display_name || file.name}`}
                        title="查看"
                      >
                        <Eye size={12} />
                      </button>
                      <button
                        onClick={() => handleDownloadManagedFile(file.name)}
                        className="secondary small"
                        aria-label={`下載文件 ${file.display_name || file.name}`}
                        title="下載"
                      >
                        <Download size={12} />
                      </button>
                      <button
                        onClick={() => onDeleteFile(file.name)}
                        className="danger small"
                        aria-label={`刪除文件 ${file.display_name || file.name}`}
                        title="刪除"
                      >
                        ✕
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => onDeleteFile(file.name)}
                      className="danger small"
                      aria-label={`刪除文件 ${file.display_name || file.name}`}
                    >
                      ✕
                    </button>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p style={{ color: '#8090b0', fontSize: '0.9rem', textAlign: 'center' }}>
              尚無文件
            </p>
          )}
        </div>
      </div>

      <div className="sidebar-section sidebar-footer">
        <button
          onClick={onOpenPromptManagement}
          className="secondary w-full"
          aria-label="開啟設置"
        >
          ⚙ 設置
        </button>
      </div>

      {managedContext && viewingFile && (
        <div className="overlay" onClick={closeViewer}>
          <div className="modal app-container" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '860px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', gap: '1rem' }}>
              <div style={{ minWidth: 0 }}>
                <h2 style={{ margin: 0 }}>{viewingFile}</h2>
                <div style={{ color: '#8090b0', fontSize: '0.92rem', marginTop: '0.25rem' }}>
                  {managedContext.appTarget.toUpperCase()} / {managedContext.language === 'zh' ? '中文' : 'English'}
                </div>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                <button className="secondary small" onClick={() => handleDownloadManagedFile(viewingFile)} title="下載">
                  <Download size={14} />
                </button>
                {fileEditable && !isEditing && (
                  <button
                    className="secondary small"
                    onClick={() => {
                      setFileEditContent(fileContent);
                      setIsEditing(true);
                    }}
                    title="編輯"
                  >
                    <Pencil size={14} />
                  </button>
                )}
                <button className="secondary small" onClick={closeViewer} title="關閉">
                  <X size={14} />
                </button>
              </div>
            </div>

            <div style={{ minHeight: '360px', maxHeight: '60vh', overflow: 'auto', border: '1px solid rgba(128, 144, 176, 0.2)', borderRadius: '12px', padding: '1rem', background: 'rgba(13, 18, 31, 0.35)' }}>
              {fileLoading ? (
                <div style={{ color: '#8090b0' }}>載入中...</div>
              ) : isEditing ? (
                <textarea
                  value={fileEditContent}
                  onChange={(e) => setFileEditContent(e.target.value)}
                  style={{
                    width: '100%',
                    minHeight: '320px',
                    background: 'transparent',
                    color: 'inherit',
                    border: 'none',
                    outline: 'none',
                    resize: 'vertical',
                    fontFamily: 'monospace',
                    fontSize: '0.92rem',
                    lineHeight: 1.6,
                  }}
                />
              ) : fileContent ? (
                <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'monospace', fontSize: '0.92rem', lineHeight: 1.6 }}>
                  {fileContent}
                </pre>
              ) : (
                <div style={{ color: '#8090b0' }}>此檔案格式不支援線上預覽，請下載查看。</div>
              )}
            </div>

            {isEditing && (
              <div className="modal-actions">
                <button className="secondary" onClick={() => setIsEditing(false)} disabled={saving}>
                  取消
                </button>
                <button onClick={() => void handleSaveEdit()} disabled={saving}>
                  {saving ? '儲存中...' : '儲存'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </aside>
  );
}
