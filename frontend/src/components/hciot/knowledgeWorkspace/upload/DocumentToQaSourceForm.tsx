import type { RefObject } from 'react';
import { AlertCircle, FileText, Type, X } from 'lucide-react';

import type { HciotLanguage } from '../../../../config/hciotTopics';
import UploadTabBody from './UploadTabBody';
import {
  MAX_TEXT_LENGTH,
  type DocFileItem,
  type DocumentSourceMode,
} from './documentToQaTypes';

interface DocumentToQaSourceFormProps {
  language: HciotLanguage;
  isEn: boolean;
  mode: DocumentSourceMode;
  fileItems: DocFileItem[];
  text: string;
  error: string | null;
  dragOver: boolean;
  fileInputRef: RefObject<HTMLInputElement | null>;
  canSubmit: boolean;
  onModeChange: (mode: DocumentSourceMode) => void;
  onTextChange: (text: string) => void;
  onDragOverChange: (dragOver: boolean) => void;
  onFileSelect: (fileList: FileList | null) => void;
  onRemoveFile: () => void;
  onStartExtraction: () => void;
  onClose: () => void;
}

function formatFileSize(size: number): string {
  return size > 1024 ? `${(size / 1024).toFixed(1)} KB` : `${size} B`;
}

function getFileExtension(file: File | undefined): string | undefined {
  return file?.name.split('.').pop()?.toLowerCase();
}

export default function DocumentToQaSourceForm({
  language,
  mode,
  fileItems,
  text,
  error,
  dragOver,
  fileInputRef,
  canSubmit,
  onModeChange,
  onTextChange,
  onDragOverChange,
  onFileSelect,
  onRemoveFile,
  onStartExtraction,
  onClose,
}: DocumentToQaSourceFormProps) {
  const selectedFile = fileItems[0]?.file;
  const ext = getFileExtension(selectedFile);
  const isCsvOrXlsx = ext === 'csv' || ext === 'xlsx';

  const uploadLabel = isCsvOrXlsx ? '開始上傳' : '開始 AI 擷取';

  return (
    <div className="hciot-doc-source-tab">
      <div className="hciot-doc-mode-toggle" role="tablist">
        <button
          type="button"
          role="tab"
          className={`hciot-doc-mode-button${mode === 'file' ? ' is-active' : ''}`}
          onClick={() => onModeChange('file')}
        >
          <FileText size={14} />
          <span>上傳檔案</span>
        </button>
        <button
          type="button"
          role="tab"
          className={`hciot-doc-mode-button${mode === 'text' ? ' is-active' : ''}`}
          onClick={() => onModeChange('text')}
        >
          <Type size={14} />
          <span>貼上文字</span>
        </button>
      </div>

      {mode === 'file' && (
        <UploadTabBody
          language={language}
          dragOver={dragOver}
          setDragOver={onDragOverChange}
          inputRef={fileInputRef}
          accept=".csv,.xlsx,.docx,.txt,.md"
          multiple={false}
          items={fileItems}
          isUploading={false}
          disabled={!canSubmit}
          dropLabelZh="點擊或拖放檔案"
          dropLabelEn="Click or drag a document"
          dropSubZh="支援 CSV, XLSX, DOCX, TXT, MD（≤ 5MB）"
          dropSubEn="CSV, XLSX, DOCX, TXT, MD (≤ 5MB)"
          countZh="份文件"
          countEn="document"
          uploadLabel={uploadLabel}
          hint={error ? (
            <div className="hciot-upload-error-banner">
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          ) : null}
          onDrop={(event) => {
            event.preventDefault();
            onDragOverChange(false);
            if (event.dataTransfer.files.length) {
              onFileSelect(event.dataTransfer.files);
            }
          }}
          onSelect={onFileSelect}
          onUpload={onStartExtraction}
          onClose={onClose}
          renderItem={(item, index) => (
            <div key={`${item.file.name}-${index}`} className="hciot-upload-file-item">
              <FileText size={16} className="hciot-icon-dark-blue" />
              <span className="hciot-upload-file-name">{item.file.name}</span>
              <span className="hciot-upload-file-size">{formatFileSize(item.file.size)}</span>
              <div className="hciot-file-actions">
                <button
                  type="button"
                  className="hciot-qa-row-delete"
                  onClick={onRemoveFile}
                  title="移除"
                >
                  <X size={14} />
                </button>
              </div>
            </div>
          )}
        />
      )}

      {mode === 'text' && (
        <div className="hciot-upload-file-body">
          <textarea
            className="hciot-doc-text-input custom-scrollbar"
            placeholder="在此貼上文章內容，AI 會自動分析並擷取問答對。"
            value={text}
            onChange={(event) => onTextChange(event.target.value)}
          />
          <div className="hciot-doc-text-meta">
            <span className={text.length > MAX_TEXT_LENGTH ? 'is-over' : ''}>
              {text.length.toLocaleString()} / {MAX_TEXT_LENGTH.toLocaleString()} 字
            </span>
          </div>
          {error && (
            <div className="hciot-upload-error-banner">
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}
          <div className="hciot-qa-footer">
            <span className="hciot-qa-count">
              {text.trim().length > 0 ? '1 段文字' : '0 段文字'}
            </span>
            <div className="hciot-qa-footer-actions">
              <button type="button" className="hciot-file-action-button" onClick={onClose}>
                取消
              </button>
              <button
                type="button"
                className="hciot-file-action-button primary"
                disabled={!canSubmit}
                onClick={onStartExtraction}
              >
                開始 AI 擷取
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
