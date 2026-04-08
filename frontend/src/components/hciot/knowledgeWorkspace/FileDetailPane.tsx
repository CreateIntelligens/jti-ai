import { Download, FileText, Save, Trash2 } from 'lucide-react';

import type { HciotLanguage } from '../../../config/hciotTopics';
import type { HciotKnowledgeFile, HciotTopicCategory } from '../../../services/api/hciot';
import {
  getFileLabel,
  getNoTopicLabel,
  NEW_VALUE,
  type FileMetadataDraft,
  type TopicOption,
} from './shared';

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
          <p className="hciot-file-kicker">Knowledge Explorer</p>
          <h2 className="hciot-file-title">
            {selectedFile ? getFileLabel(selectedFile) : (language === 'zh' ? '檔案管理' : 'File Manager')}
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
            <span>{language === 'zh' ? '下載' : 'Download'}</span>
          </button>
          <button
            type="button"
            className="hciot-file-action-button danger"
            onClick={onDelete}
            disabled={!selectedFile || deleting}
          >
            <Trash2 size={15} />
            <span>{deleting ? (language === 'zh' ? '刪除中...' : 'Deleting...') : (language === 'zh' ? '刪除' : 'Delete')}</span>
          </button>
          <button
            type="button"
            className="hciot-file-action-button primary"
            onClick={onSave}
            disabled={!selectedFile || saving || uploading || deleting || !hasUnsavedChanges}
          >
            <Save size={15} />
            <span>{saving ? (language === 'zh' ? '儲存中...' : 'Saving...') : (language === 'zh' ? '儲存變更' : 'Save Changes')}</span>
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
                {language === 'zh' ? '科別 / 主題' : 'Category / Topic'}
              </label>
              <div className="hciot-file-metadata-controls">
                <select
                  value={draft.categoryId}
                  onChange={(event) => onCategoryChange(event.target.value)}
                  className="hciot-file-select"
                  disabled={saving}
                >
                  {categoryOptions.map((category) => (
                    <option key={category.id} value={category.id}>
                      {category.labels[language]}
                    </option>
                  ))}
                  <option value={NEW_VALUE}>
                    {language === 'zh' ? '＋ 新增科別' : '+ New category'}
                  </option>
                </select>

                <span className="hciot-file-path-separator">/</span>

                <select
                  value={draft.topicId}
                  onChange={(event) => onTopicChange(event.target.value)}
                  className="hciot-file-select"
                  disabled={saving || !draft.categoryId}
                >
                  <option value="">
                    {draft.categoryId
                      ? getNoTopicLabel(language)
                      : (language === 'zh' ? '先選科別' : 'Select category first')}
                  </option>
                  {topicOptions.map((topic) => (
                    <option key={topic.id} value={topic.id}>
                      {topic.labels[language]}
                    </option>
                  ))}
                  {draft.categoryId ? (
                    <option value={NEW_VALUE}>
                      {language === 'zh' ? '＋ 新增主題' : '+ New topic'}
                    </option>
                  ) : null}
                </select>
              </div>
            </div>

            {draft.categoryId === NEW_VALUE ? (
              <div className="hciot-file-inline-create">
                <input
                  className="hciot-file-input"
                  placeholder={language === 'zh' ? '新科別中文名稱' : 'New category (zh)'}
                  value={draft.categoryLabelZh}
                  onChange={(event) => onDraftChange({ categoryLabelZh: event.target.value })}
                />
                <input
                  className="hciot-file-input"
                  placeholder={language === 'zh' ? '新科別英文名稱' : 'New category (en)'}
                  value={draft.categoryLabelEn}
                  onChange={(event) => onDraftChange({ categoryLabelEn: event.target.value })}
                />
              </div>
            ) : null}

            {draft.topicId === NEW_VALUE ? (
              <div className="hciot-file-inline-create">
                <input
                  className="hciot-file-input"
                  placeholder={language === 'zh' ? '新主題中文名稱' : 'New topic (zh)'}
                  value={draft.topicLabelZh}
                  onChange={(event) => onDraftChange({ topicLabelZh: event.target.value })}
                />
                <input
                  className="hciot-file-input"
                  placeholder={language === 'zh' ? '新主題英文名稱' : 'New topic (en)'}
                  value={draft.topicLabelEn}
                  onChange={(event) => onDraftChange({ topicLabelEn: event.target.value })}
                />
              </div>
            ) : null}
          </section>

          <section className="hciot-file-editor-panel">
            <div className="hciot-file-editor-meta">
              <span>{selectedFile.content_type || 'text/plain'}</span>
              <span>{selectedFile.size ? `${Math.max(1, Math.round(selectedFile.size / 1024))} KB` : '0 KB'}</span>
              <span>{fileEditable ? (language === 'zh' ? '可直接編輯' : 'Editable') : (language === 'zh' ? '僅預覽/下載' : 'Preview only')}</span>
            </div>

            {loadingContent ? (
              <div className="hciot-file-editor-empty">{language === 'zh' ? '載入內容中...' : 'Loading content...'}</div>
            ) : fileEditable ? (
              <textarea
                className="hciot-file-textarea"
                value={editorText}
                onChange={(event) => onEditorTextChange(event.target.value)}
                spellCheck={false}
              />
            ) : (
              <div className="hciot-file-editor-empty">
                <p>{contentMessage || (language === 'zh' ? '此檔案格式不支援線上編輯' : 'This file type is not editable online')}</p>
                <p>{language === 'zh' ? '你仍然可以調整科別 / 主題關聯並下載檔案。' : 'You can still update category/topic metadata and download the file.'}</p>
              </div>
            )}
          </section>
        </>
      ) : (
        <div className="hciot-file-empty">
          <FileText size={28} />
          <div>
            <h3>{language === 'zh' ? '從左側 Explorer 選擇檔案' : 'Select a file from the Explorer'}</h3>
            <p>
              {language === 'zh'
                ? '搜尋、展開科別與主題，右側會直接進入內容編輯。'
                : 'Search the tree, expand categories and topics, then edit content directly here.'}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
