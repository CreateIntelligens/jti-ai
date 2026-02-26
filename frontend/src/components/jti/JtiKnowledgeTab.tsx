import { useState, useRef } from 'react';
import { Upload, FileText, Trash2, Download, Eye, Pencil, X } from 'lucide-react';
import ConfirmDialog from '../ConfirmDialog';

interface KBFile {
  name: string;
  display_name: string;
  size?: number;
  editable?: boolean;
}

export interface JtiKnowledgeTabProps {
  language: string;
  kbFiles: KBFile[];
  kbLoading: boolean;
  uploading: boolean;
  successMsg: string | null;
  // Upload
  onUploadFiles: (files: FileList | File[]) => Promise<void>;
  // File actions
  onViewFile: (filename: string) => void;
  onDownloadFile: (filename: string) => void;
  onDeleteFileClick: (filename: string) => void;
  // Delete confirm
  confirmDeleteFile: string | null;
  deletingFile: boolean;
  onDeleteFileConfirm: () => Promise<void>;
  onDeleteFileCancel: () => void;
  // Viewer
  viewingFile: string | null;
  fileContent: string;
  fileEditable: boolean;
  fileLoading: boolean;
  isEditing: boolean;
  fileEditContent: string;
  saving: boolean;
  onStartEdit: () => void;
  onCancelEdit: () => void;
  onSaveEdit: () => Promise<void>;
  onFileEditContentChange: (content: string) => void;
  onCloseViewer: () => void;
}

export default function JtiKnowledgeTab({
  language,
  kbFiles,
  kbLoading,
  uploading,
  successMsg,
  onUploadFiles,
  onViewFile,
  onDownloadFile,
  onDeleteFileClick,
  confirmDeleteFile,
  deletingFile,
  onDeleteFileConfirm,
  onDeleteFileCancel,
  viewingFile,
  fileContent,
  fileEditable,
  fileLoading,
  isEditing,
  fileEditContent,
  saving,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  onFileEditContentChange,
  onCloseViewer,
}: JtiKnowledgeTabProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  if (kbLoading) {
    return <div className="jti-settings-loading">載入中...</div>;
  }

  return (
    <>
      {successMsg && (
        <div className="jti-success-banner">{successMsg}</div>
      )}

      {/* Upload area */}
      <div
        className={`jti-kb-upload-zone${dragOver ? ' drag-over' : ''}${uploading ? ' uploading' : ''}`}
        onClick={() => !uploading && fileInputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => { setDragOver(false); }}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          if (e.dataTransfer.files.length > 0) onUploadFiles(e.dataTransfer.files);
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          hidden
          onChange={(e) => {
            if (e.target.files && e.target.files.length > 0) {
              onUploadFiles(e.target.files);
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
                onClick={() => onViewFile(file.name)}
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
                  onClick={() => onViewFile(file.name)}
                  title="檢視"
                >
                  <Eye size={12} />
                </button>
                <button
                  className="jti-btn small secondary"
                  onClick={() => onDownloadFile(file.name)}
                  title="下載"
                >
                  <Download size={12} />
                </button>
                <button
                  className="jti-btn small secondary"
                  onClick={() => onDeleteFileClick(file.name)}
                  title="刪除"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <ConfirmDialog
        isOpen={!!confirmDeleteFile}
        message="確定要刪除此檔案嗎？"
        onConfirm={onDeleteFileConfirm}
        onCancel={onDeleteFileCancel}
        loading={deletingFile}
      />

      {/* File viewer/editor modal */}
      {viewingFile && (
        <div className="jti-viewer-overlay" onClick={onCloseViewer}>
          <div className="jti-viewer-modal" onClick={e => e.stopPropagation()}>
            <div className="jti-viewer-header">
              <div className="jti-viewer-title">
                <FileText size={16} className="jti-viewer-title-icon" />
                <span className="jti-viewer-title-text">{viewingFile}</span>
              </div>
              <div className="jti-viewer-header-actions">
                <button className="jti-btn small secondary" onClick={() => onDownloadFile(viewingFile)} title="下載">
                  <Download size={14} />
                </button>
                {fileEditable && !isEditing && (
                  <button className="jti-btn small secondary" onClick={onStartEdit} title="編輯">
                    <Pencil size={14} />
                  </button>
                )}
                <button className="jti-btn small secondary" onClick={onCloseViewer}>
                  <X size={14} />
                </button>
              </div>
            </div>

            <div className="jti-viewer-body">
              {fileLoading ? (
                <div className="jti-viewer-loading">載入中...</div>
              ) : isEditing ? (
                <textarea
                  className="jti-viewer-textarea"
                  value={fileEditContent}
                  onChange={e => onFileEditContentChange(e.target.value)}
                />
              ) : fileContent ? (
                <pre className="jti-viewer-pre">{fileContent}</pre>
              ) : (
                <div className="jti-viewer-empty">
                  此檔案格式不支援線上預覽，請下載查看
                </div>
              )}
            </div>

            {isEditing && (
              <div className="jti-viewer-footer">
                <button className="jti-btn small secondary" onClick={onCancelEdit} disabled={saving}>
                  取消
                </button>
                <button
                  className="jti-btn small save"
                  onClick={onSaveEdit}
                  disabled={saving}
                >
                  {saving ? '儲存中...' : '儲存'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
