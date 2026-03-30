import { useState, useRef, useEffect, useMemo } from 'react';
import { Upload, FileText, Trash2, Download, Pencil, X } from 'lucide-react';
import ConfirmDialog from '../ConfirmDialog';
import HciotTopicEditor from './HciotTopicEditor';
import { NEW_VALUE, slugify } from './knowledgeWorkspace/shared';
import * as api from '../../services/api';

interface KBFile {
  name: string;
  display_name?: string;
  size?: number;
  editable?: boolean;
}

export interface HciotKnowledgeTabProps {
  language: string;
  kbFiles: KBFile[];
  kbLoading: boolean;
  uploading: boolean;
  successMsg: string | null;
  onUploadFiles: (files: FileList | File[], topicOpts?: TopicUploadOpts) => Promise<void>;
  onViewFile: (filename: string) => void;
  onDownloadFile: (filename: string) => void;
  onDeleteFileClick: (filename: string) => void;
  confirmDeleteFile: string | null;
  deletingFiles: string[];
  onDeleteFileConfirm: () => Promise<void>;
  onDeleteFileCancel: () => void;
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

export interface TopicUploadOpts {
  categoryId?: string;
  topicId?: string;
  categoryLabelZh?: string;
  categoryLabelEn?: string;
  topicLabelZh?: string;
  topicLabelEn?: string;
}

export default function HciotKnowledgeTab({
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
  deletingFiles,
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
}: HciotKnowledgeTabProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const lang = language === 'en' ? 'en' : 'zh' as const;

  // Topic association state
  const [categories, setCategories] = useState<api.HciotTopicCategory[]>([]);
  const [selectedCategoryId, setSelectedCategoryId] = useState('');
  const [selectedTopicId, setSelectedTopicId] = useState('');
  const [newCategoryLabelZh, setNewCategoryLabelZh] = useState('');
  const [newCategoryLabelEn, setNewCategoryLabelEn] = useState('');
  const [newTopicLabelZh, setNewTopicLabelZh] = useState('');
  const [newTopicLabelEn, setNewTopicLabelEn] = useState('');

  const isNewCategory = selectedCategoryId === NEW_VALUE;
  const isNewTopic = selectedTopicId === NEW_VALUE;
  const effectiveCategoryId = isNewCategory ? slugify(newCategoryLabelEn || newCategoryLabelZh) : selectedCategoryId;

  const selectedCategory = useMemo(
    () => categories.find((c) => c.id === selectedCategoryId),
    [categories, selectedCategoryId],
  );
  const topicsInCategory = selectedCategory?.topics ?? [];

  const effectiveTopicId = isNewTopic ? slugify(newTopicLabelEn || newTopicLabelZh) : selectedTopicId;

  useEffect(() => {
    api.listHciotTopicsAdmin()
      .then((data) => setCategories(data.categories || []))
      .catch(() => setCategories([]));
  }, []);

  // Reset topic when category changes
  useEffect(() => {
    setSelectedTopicId('');
    setNewTopicLabelZh('');
    setNewTopicLabelEn('');
  }, [selectedCategoryId]);

  const buildTopicOpts = (): TopicUploadOpts | undefined => {
    if (!effectiveCategoryId || !effectiveTopicId) return undefined;
    const existingTopic = topicsInCategory.find((t) => t.id === selectedTopicId);
    // Extract just the topic slug if selectedTopicId is a full "cat/topic" format
    const topicSlug = isNewTopic
      ? effectiveTopicId
      : (selectedTopicId.includes('/') ? selectedTopicId.split('/').slice(1).join('/') : selectedTopicId);
    return {
      categoryId: effectiveCategoryId,
      topicId: topicSlug,
      categoryLabelZh: isNewCategory ? newCategoryLabelZh.trim() || undefined : undefined,
      categoryLabelEn: isNewCategory ? newCategoryLabelEn.trim() || undefined : undefined,
      topicLabelZh: isNewTopic
        ? newTopicLabelZh.trim() || undefined
        : existingTopic?.labels.zh,
      topicLabelEn: isNewTopic
        ? newTopicLabelEn.trim() || undefined
        : existingTopic?.labels.en,
    };
  };

  const handleUpload = (files: FileList | File[]) => {
    void onUploadFiles(files, buildTopicOpts());
  };

  if (kbLoading) {
    return <div className="jti-settings-loading">載入中...</div>;
  }

  return (
    <>
      {successMsg && (
        <div className="jti-success-banner">{successMsg}</div>
      )}

      {/* Topic association fields */}
      <div className="hciot-kb-topic-section">
        <p className="hciot-kb-topic-hint">
          {lang === 'zh'
            ? '📋 上傳 CSV（含 q 欄位）時，題目將自動匯入指定科別／主題'
            : '📋 When CSV has a q column, questions auto-import to the selected category/topic'}
        </p>

        <div className="hciot-kb-selectors">
          {/* Category dropdown */}
          <div className="hciot-kb-field">
            <label className="hciot-kb-label">
              {lang === 'zh' ? '科別' : 'Category'}
            </label>
            <select
              className="hciot-kb-select"
              value={selectedCategoryId}
              onChange={(e) => setSelectedCategoryId(e.target.value)}
            >
              <option value="">
                {lang === 'zh' ? '— 不指定 —' : '— None —'}
              </option>
              {categories.map((cat) => (
                <option key={cat.id} value={cat.id}>
                  {cat.labels[lang]}
                </option>
              ))}
              <option value={NEW_VALUE}>
                {lang === 'zh' ? '＋ 新增科別' : '+ New category'}
              </option>
            </select>
          </div>

          {/* Topic dropdown (only when a category is selected) */}
          {(effectiveCategoryId || isNewCategory) && (
            <div className="hciot-kb-field">
              <label className="hciot-kb-label">
                {lang === 'zh' ? '主題' : 'Topic'}
              </label>
              <select
                className="hciot-kb-select"
                value={selectedTopicId}
                onChange={(e) => setSelectedTopicId(e.target.value)}
                disabled={isNewCategory && !effectiveCategoryId}
              >
                <option value="">
                  {lang === 'zh' ? '— 不指定 —' : '— None —'}
                </option>
                {!isNewCategory && topicsInCategory.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.labels[lang]}
                  </option>
                ))}
                <option value={NEW_VALUE}>
                  {lang === 'zh' ? '＋ 新增主題' : '+ New topic'}
                </option>
              </select>
            </div>
          )}
        </div>

        {/* New category inputs */}
        {isNewCategory && (
          <div className="hciot-kb-new-fields">
            <input
              className="hciot-kb-input"
              placeholder={lang === 'zh' ? '中文名稱' : 'Label (zh)'}
              value={newCategoryLabelZh}
              onChange={(e) => setNewCategoryLabelZh(e.target.value)}
            />
            <input
              className="hciot-kb-input"
              placeholder={lang === 'zh' ? '英文名稱' : 'Label (en)'}
              value={newCategoryLabelEn}
              onChange={(e) => setNewCategoryLabelEn(e.target.value)}
            />
          </div>
        )}

        {/* New topic inputs */}
        {isNewTopic && effectiveCategoryId && (
          <div className="hciot-kb-new-fields">
            <input
              className="hciot-kb-input"
              placeholder={lang === 'zh' ? '主題中文名' : 'Topic label (zh)'}
              value={newTopicLabelZh}
              onChange={(e) => setNewTopicLabelZh(e.target.value)}
            />
            <input
              className="hciot-kb-input"
              placeholder={lang === 'zh' ? '主題英文名' : 'Topic label (en)'}
              value={newTopicLabelEn}
              onChange={(e) => setNewTopicLabelEn(e.target.value)}
            />
          </div>
        )}
      </div>

      {/* Upload area */}
      <div
        className={`jti-kb-upload-zone${dragOver ? ' drag-over' : ''}${uploading ? ' uploading' : ''}`}
        onClick={() => !uploading && fileInputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => { setDragOver(false); }}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          if (e.dataTransfer.files.length > 0) handleUpload(e.dataTransfer.files);
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          hidden
          onChange={(e) => {
            if (e.target.files && e.target.files.length > 0) {
              handleUpload(e.target.files);
              e.target.value = '';
            }
          }}
        />
        <Upload size={24} className="jti-kb-upload-icon" />
        <p className="jti-kb-upload-text">
          {uploading ? '上傳中...' : '點擊或拖放檔案上傳'}
        </p>
        <p className="jti-kb-upload-hint">
          支援 PDF、TXT、Word、CSV 等格式
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
          {kbFiles.map((file) => {
            const isDeleting = deletingFiles.includes(file.name);
            return (
              <div key={file.name} className="jti-kb-file-item">
                <div
                  className="jti-kb-file-info"
                  onClick={() => onViewFile(file.name)}
                >
                  <FileText size={16} className="jti-kb-file-icon" />
                  <span className="jti-kb-file-name">{file.display_name || file.name}</span>
                  {file.size && (
                    <span className="jti-kb-file-size">
                      {file.size > 1024 ? `${(file.size / 1024).toFixed(1)}KB` : `${file.size}B`}
                    </span>
                  )}
                </div>
                <div className="jti-kb-file-actions">
                  <button
                    className="jti-btn small secondary"
                    onClick={() => onDownloadFile(file.name)}
                    title="下載"
                    disabled={isDeleting}
                  >
                    <Download size={12} />
                  </button>
                  <button
                    className="jti-btn small secondary"
                    onClick={() => onDeleteFileClick(file.name)}
                    title={isDeleting ? '刪除中' : '刪除'}
                    disabled={isDeleting}
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <ConfirmDialog
        isOpen={!!confirmDeleteFile}
        message="確定要刪除此檔案嗎？"
        onConfirm={onDeleteFileConfirm}
        onCancel={onDeleteFileCancel}
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

      {/* Topic editor section */}
      <HciotTopicEditor
        language={lang}
        categories={categories}
        onCategoriesChange={setCategories}
      />
    </>
  );
}
