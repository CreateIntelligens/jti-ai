import { Download, FileText, Save, Trash2 } from 'lucide-react';

import HciotSelect from '../../../hciot/HciotSelect';
import type { HciotLanguage } from '../../../../config/hciotTopics';
import type { HciotKnowledgeFile, HciotTopicCategory } from '../../../../services/api/hciot';
import { getFileLabel, NEW_VALUE, type FileMetadataDraft, type TopicOption } from '../topicUtils';
import { getNoTopicLabel } from '../explorer/explorerTree';

export interface FileDetailPaneState {
  selectedFile: HciotKnowledgeFile | null;
  currentPathLabel: string;
  statusMessage: string | null;
  deleting: boolean;
  saving: boolean;
  uploading: boolean;
  hasUnsavedChanges: boolean;
  draft: FileMetadataDraft;
  fileEditable: boolean;
  loadingContent: boolean;
  contentMessage: string | null;
  editorText: string;
}

export interface FileDetailPaneActions {
  onDownload: () => void;
  onDelete: () => void;
  onSave: () => void;
  onCategoryChange: (value: string) => void;
  onTopicChange: (value: string) => void;
  onDraftChange: (changes: Partial<FileMetadataDraft>) => void;
  onEditorTextChange: (value: string) => void;
}

interface FileDetailPaneProps {
  language: HciotLanguage;
  state: FileDetailPaneState;
  actions: FileDetailPaneActions;
  categoryOptions: HciotTopicCategory[];
  topicOptions: TopicOption[];
}

export default function FileDetailPane({
  language,
  state,
  actions,
  categoryOptions,
  topicOptions,
}: FileDetailPaneProps) {
  const {
    selectedFile,
    currentPathLabel,
    statusMessage,
    deleting,
    saving,
    uploading,
    hasUnsavedChanges,
    draft,
    fileEditable,
    loadingContent,
    contentMessage,
    editorText,
  } = state;

  const {
    onDownload,
    onDelete,
    onSave,
    onCategoryChange,
    onTopicChange,
    onDraftChange,
    onEditorTextChange,
  } = actions;

  if (!selectedFile) {
    return (
      <div className="qa-workspace-file-editor-empty-state-container">
        <div className="qa-workspace-file-editor-empty-state-card">
          <div className="qa-workspace-file-editor-empty-state-icon-wrap">
            <FileText size={48} className="qa-workspace-file-editor-empty-state-icon" />
          </div>
          <h3 className="qa-workspace-file-editor-empty-state-title">知識庫管理工作區</h3>
          <p className="qa-workspace-file-editor-empty-state-description">
            請從左側檔案樹選擇檔案，或點擊左上方「＋」按鈕新增內容。
          </p>

          <div className="hciot-rag-flow-diagram">
            <div className="hciot-rag-flow-step">
              <span className="step-num">1</span>
              <span className="step-text">選取知識檔案</span>
            </div>
            <div className="hciot-rag-flow-arrow">➔</div>
            <div className="hciot-rag-flow-step">
              <span className="step-num">2</span>
              <span className="step-text">編輯/關聯主題</span>
            </div>
            <div className="hciot-rag-flow-arrow">➔</div>
            <div className="hciot-rag-flow-step">
              <span className="step-num">3</span>
              <span className="step-text">更新 RAG 索引</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const showTopicMetadata = Boolean(selectedFile.topic_id);

  return (
    <div className="qa-workspace-file-editor">
      <div className="qa-workspace-file-header">
        <div>
          <p className="qa-workspace-file-kicker">知識庫</p>
          <h2 className="qa-workspace-file-title">
            {getFileLabel(selectedFile)}
          </h2>
          <p className="qa-workspace-file-path">{currentPathLabel}</p>
        </div>

        <div className="qa-workspace-file-actions">
          <button
            type="button"
            className="qa-workspace-file-action-button"
            onClick={onDownload}
            disabled={deleting}
          >
            <Download size={15} />
            <span>下載</span>
          </button>
          <button
            type="button"
            className="qa-workspace-file-action-button danger"
            onClick={onDelete}
            disabled={deleting}
          >
            <Trash2 size={15} />
            <span>{deleting ? '刪除中...' : '刪除'}</span>
          </button>
          <button
            type="button"
            className="qa-workspace-file-action-button primary"
            onClick={onSave}
            disabled={saving || uploading || deleting || !hasUnsavedChanges}
          >
            <Save size={15} />
            <span>{saving ? '儲存中...' : '儲存變更'}</span>
          </button>
        </div>
      </div>

      {statusMessage ? (
        <div className="qa-workspace-file-status-banner">{statusMessage}</div>
      ) : null}

      {showTopicMetadata ? (
        <section className="qa-workspace-file-metadata">
          <div className="qa-workspace-file-metadata-group">
            <label className="qa-workspace-file-metadata-label">
              科別 / 主題
            </label>
            <div className="qa-workspace-file-metadata-controls">
              <HciotSelect
                className="qa-workspace-file-select"
                value={draft.categoryId}
                onChange={onCategoryChange}
                disabled={saving}
                options={[
                  ...categoryOptions.map((category) => ({ value: category.id, label: category.label })),
                  { value: NEW_VALUE, label: '＋ 新增科別' },
                ]}
              />

              <span className="qa-workspace-file-path-separator">/</span>

              <HciotSelect
                className="qa-workspace-file-select"
                value={draft.topicId}
                onChange={onTopicChange}
                disabled={saving || !draft.categoryId}
                options={[
                  {
                    value: '',
                    label: draft.categoryId
                      ? getNoTopicLabel(language)
                      : '先選科別',
                  },
                  ...topicOptions.map((topic) => ({ value: topic.id, label: topic.label })),
                  ...(draft.categoryId
                    ? [{ value: NEW_VALUE, label: '＋ 新增主題' }]
                    : []),
                ]}
              />
            </div>
          </div>

          {draft.categoryId === NEW_VALUE ? (
            <div className="qa-workspace-file-inline-create">
              <input
                className="qa-workspace-file-input"
                placeholder="新科別名稱"
                value={draft.categoryLabel}
                onChange={(event) => onDraftChange({ categoryLabel: event.target.value })}
              />
            </div>
          ) : null}

          {draft.topicId === NEW_VALUE ? (
            <div className="qa-workspace-file-inline-create">
              <input
                className="qa-workspace-file-input"
                placeholder="新主題名稱"
                value={draft.topicLabel}
                onChange={(event) => onDraftChange({ topicLabel: event.target.value })}
              />
            </div>
          ) : null}
        </section>
      ) : null}

      <section className="qa-workspace-file-editor-panel">
        <div className="qa-workspace-file-editor-meta">
          <span>{selectedFile.content_type || 'text/plain'}</span>
          <span>{selectedFile.size ? `${Math.max(1, Math.round(selectedFile.size / 1024))} KB` : '0 KB'}</span>
          <span>{fileEditable ? '可直接編輯' : '僅預覽/下載'}</span>
        </div>

        {loadingContent ? (
          <div className="qa-workspace-file-editor-empty">載入內容中...</div>
        ) : fileEditable ? (
          <textarea
            className="qa-workspace-file-textarea"
            value={editorText}
            onChange={(event) => onEditorTextChange(event.target.value)}
            spellCheck={false}
          />
        ) : (
          <div className="qa-workspace-file-editor-empty">
            <p>{contentMessage || '此檔案格式不支援線上編輯'}</p>
            <p>你仍然可以調整科別 / 主題關聯並下載檔案。</p>
          </div>
        )}
      </section>
    </div>
  );
}
