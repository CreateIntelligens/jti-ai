import { useState, useRef, useEffect, useMemo } from 'react';
import { Upload, FileText, Trash2, Download, Pencil, X } from 'lucide-react';
import HciotSelect from './HciotSelect';
import ConfirmDialog from '../ConfirmDialog';
import HciotTopicEditor from './HciotTopicEditor';
import { missingLabelMessage, NEW_VALUE, normalizeLabel, slugify } from '../_shared/qaKnowledgeWorkspace/topicUtils';
import * as api from '../../services/api';
import { useOverlayPressClose } from '../../hooks/useOverlayPressClose';

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
  categoryLabel?: string;
  topicLabel?: string;
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
  const viewerOverlayPressClose = useOverlayPressClose(onCloseViewer);

  // Topic association state
  const [categories, setCategories] = useState<api.HciotTopicCategory[]>([]);
  const [selectedCategoryId, setSelectedCategoryId] = useState('');
  const [selectedTopicId, setSelectedTopicId] = useState('');
  const [newCategoryLabel, setNewCategoryLabel] = useState('');
  const [newTopicLabel, setNewTopicLabel] = useState('');

  const isNewCategory = selectedCategoryId === NEW_VALUE;
  const isNewTopic = selectedTopicId === NEW_VALUE;
  const newCategoryLabelValue = normalizeLabel(newCategoryLabel);
  const newTopicLabelValue = normalizeLabel(newTopicLabel);
  const effectiveCategoryId = isNewCategory && newCategoryLabelValue ? slugify(newCategoryLabelValue) : selectedCategoryId;

  const selectedCategory = useMemo(
    () => categories.find((c) => c.id === selectedCategoryId),
    [categories, selectedCategoryId],
  );
  const topicsInCategory = selectedCategory?.topics ?? [];

  const effectiveTopicId = isNewTopic && newTopicLabelValue ? slugify(newTopicLabelValue) : selectedTopicId;

  useEffect(() => {
    api.listHciotTopicsAdmin(lang)
      .then((data) => setCategories(data.categories || []))
      .catch(() => setCategories([]));
  }, [lang]);

  // Reset topic when category changes
  useEffect(() => {
    setSelectedTopicId('');
    setNewTopicLabel('');
  }, [selectedCategoryId]);

  const t = {
    hint: '📋 上傳 CSV（含 q 欄位）時，題目將自動匯入指定科別／主題',
    category: '科別',
    topic: '主題',
    none: '— 不指定 —',
    newCat: '＋ 新增科別',
    newTopic: '＋ 新增主題',
    catName: '科別名稱',
    topicName: '主題名稱',
    upload: '點擊或拖放檔案上傳',
    uploading: '上傳中...',
    formatHint: '支援 PDF、TXT、Word、CSV 等格式',
    fileCount: (count: number) => `共 ${count} 個檔案（${lang === 'zh' ? '中文' : 'English'} 知識庫）`,
    empty: '知識庫尚無檔案',
    confirmDelete: '確定要刪除此檔案嗎？',
  };

  const buildTopicOpts = (): TopicUploadOpts | undefined => {
    if (!effectiveCategoryId || !effectiveTopicId) return undefined;

    const existingTopic = topicsInCategory.find((t) => t.id === selectedTopicId);
    const topicSlug = isNewTopic
      ? effectiveTopicId
      : (selectedTopicId.split('/').pop() || selectedTopicId);

    return {
      categoryId: effectiveCategoryId,
      topicId: topicSlug,
      categoryLabel: isNewCategory ? newCategoryLabelValue ?? undefined : undefined,
      topicLabel: isNewTopic ? newTopicLabelValue ?? undefined : existingTopic?.label,
    };
  };

  const handleUpload = (files: FileList | File[]) => {
    if (isNewCategory && !newCategoryLabelValue) {
      alert(missingLabelMessage('category', lang));
      return;
    }
    if (isNewTopic && !newTopicLabelValue) {
      alert(missingLabelMessage('topic', lang));
      return;
    }
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
        <p className="hciot-kb-topic-hint">{t.hint}</p>

        <div className="hciot-kb-selectors">
          <div className="hciot-kb-field">
            <label className="hciot-kb-label">{t.category}</label>
            <HciotSelect
              className="hciot-kb-select"
              value={selectedCategoryId}
              onChange={setSelectedCategoryId}
              options={[
                { value: '', label: t.none },
                ...categories.map((cat) => ({ value: cat.id, label: cat.label })),
                { value: NEW_VALUE, label: t.newCat },
              ]}
            />
          </div>

          {(effectiveCategoryId || isNewCategory) && (
            <div className="hciot-kb-field">
              <label className="hciot-kb-label">{t.topic}</label>
              <HciotSelect
                className="hciot-kb-select"
                value={selectedTopicId}
                onChange={setSelectedTopicId}
                disabled={isNewCategory && !effectiveCategoryId}
                options={[
                  { value: '', label: t.none },
                  ...(!isNewCategory ? topicsInCategory.map((t) => ({ value: t.id, label: t.label })) : []),
                  { value: NEW_VALUE, label: t.newTopic },
                ]}
              />
            </div>
          )}
        </div>

        {isNewCategory && (
          <div className="hciot-kb-new-fields">
            <input className="hciot-kb-input" placeholder={t.catName} value={newCategoryLabel} onChange={(e) => setNewCategoryLabel(e.target.value)} />
          </div>
        )}

        {isNewTopic && effectiveCategoryId && (
          <div className="hciot-kb-new-fields">
            <input className="hciot-kb-input" placeholder={t.topicName} value={newTopicLabel} onChange={(e) => setNewTopicLabel(e.target.value)} />
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
          {uploading ? t.uploading : t.upload}
        </p>
        <p className="jti-kb-upload-hint">{t.formatHint}</p>
      </div>

      {/* File list */}
      <div className="jti-kb-file-count">{t.fileCount(kbFiles.length)}</div>
      {kbFiles.length === 0 ? (
        <div className="jti-kb-empty">{t.empty}</div>
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
        message={t.confirmDelete}
        onConfirm={onDeleteFileConfirm}
        onCancel={onDeleteFileCancel}
      />

      {/* File viewer/editor modal */}
      {viewingFile && (
        <div className="jti-viewer-overlay" {...viewerOverlayPressClose}>
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
