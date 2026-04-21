import { Download, FileText, Save, Trash2 } from 'lucide-react';

import HciotSelect from '../../HciotSelect';
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
  return (
    <div className="hciot-file-editor">
      <div className="hciot-file-header">
        <div>
          <p className="hciot-file-kicker">知識庫</p>
          <h2 className="hciot-file-title">
            {selectedFile ? getFileLabel(selectedFile) : '檔案管理'}
          </h2>
          <p className="hciot-file-path">{currentPathLabel}</p>
        </div>

        <div className="hciot-file-actions">
          <button
            type="button"
            className="hciot-file-action-button"
            onClick={onDownload}
            disabled={!selectedFile || deleting}
          >
            <Download size={15} />
            <span>下載</span>
          </button>
          <button
            type="button"
            className="hciot-file-action-button danger"
            onClick={onDelete}
            disabled={!selectedFile || deleting}
          >
            <Trash2 size={15} />
            <span>{deleting ? '刪除中...' : '刪除'}</span>
          </button>
          <button
            type="button"
            className="hciot-file-action-button primary"
            onClick={onSave}
            disabled={!selectedFile || saving || uploading || deleting || !hasUnsavedChanges}
          >
            <Save size={15} />
            <span>{saving ? '儲存中...' : '儲存變更'}</span>
          </button>
        </div>
      </div>

      {statusMessage ? (
        <div className="hciot-file-status-banner">{statusMessage}</div>
      ) : null}

      {selectedFile ? (
        <>
          <section className="hciot-file-metadata">
            <div className="hciot-file-metadata-group">
              <label className="hciot-file-metadata-label">
                科別 / 主題
              </label>
              <div className="hciot-file-metadata-controls">
                <HciotSelect
                  className="hciot-file-select"
                  value={draft.categoryId}
                  onChange={onCategoryChange}
                  disabled={saving}
                  options={[
                    ...categoryOptions.map((category) => ({ value: category.id, label: category.labels[language] })),
                    { value: NEW_VALUE, label: '＋ 新增科別' },
                  ]}
                />

                <span className="hciot-file-path-separator">/</span>

                <HciotSelect
                  className="hciot-file-select"
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
                    ...topicOptions.map((topic) => ({ value: topic.id, label: topic.labels[language] })),
                    ...(draft.categoryId
                      ? [{ value: NEW_VALUE, label: '＋ 新增主題' }]
                      : []),
                  ]}
                />
              </div>
            </div>

            {draft.categoryId === NEW_VALUE ? (
              <div className="hciot-file-inline-create">
                <input
                  className="hciot-file-input"
                  placeholder="新科別名稱"
                  value={draft.categoryLabelZh}
                  onChange={(event) => onDraftChange({ categoryLabelZh: event.target.value })}
                />
              </div>
            ) : null}

            {draft.topicId === NEW_VALUE ? (
              <div className="hciot-file-inline-create">
                <input
                  className="hciot-file-input"
                  placeholder="新主題名稱"
                  value={draft.topicLabelZh}
                  onChange={(event) => onDraftChange({ topicLabelZh: event.target.value })}
                />
              </div>
            ) : null}
          </section>

          <section className="hciot-file-editor-panel">
            <div className="hciot-file-editor-meta">
              <span>{selectedFile.content_type || 'text/plain'}</span>
              <span>{selectedFile.size ? `${Math.max(1, Math.round(selectedFile.size / 1024))} KB` : '0 KB'}</span>
              <span>{fileEditable ? '可直接編輯' : '僅預覽/下載'}</span>
            </div>

            {loadingContent ? (
              <div className="hciot-file-editor-empty">載入內容中...</div>
            ) : fileEditable ? (
              <textarea
                className="hciot-file-textarea"
                value={editorText}
                onChange={(event) => onEditorTextChange(event.target.value)}
                spellCheck={false}
              />
            ) : (
              <div className="hciot-file-editor-empty">
                <p>{contentMessage || '此檔案格式不支援線上編輯'}</p>
                <p>你仍然可以調整科別 / 主題關聯並下載檔案。</p>
              </div>
            )}
          </section>
        </>
      ) : (
        <div className="hciot-file-empty">
          <FileText size={28} />
          <div>
            <h3>從左側檔案樹選擇檔案</h3>
            <p>搜尋、展開科別與主題，右側會直接進入內容編輯。</p>
          </div>
        </div>
      )}
    </div>
  );
}
