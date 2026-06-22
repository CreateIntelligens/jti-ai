import type { RefObject } from 'react';
import { AlertCircle, Download, FileText, Table, Type, X } from 'lucide-react';

import type { QaLanguage } from '../../../../config/qaTopics';
import { downloadBlob } from '../../../../utils/download';
import UploadTabBody from './UploadTabBody';
import {
  MAX_TEXT_LENGTH,
  type DocFileItem,
  type DocumentSourceMode,
} from './documentToQaTypes';

interface DocumentToQaSourceFormProps {
  language: QaLanguage;
  isEn: boolean;
  mode: DocumentSourceMode;
  fileItems: DocFileItem[];
  text: string;
  error: string | null;
  dragOver: boolean;
  fileInputRef: RefObject<HTMLInputElement | null>;
  canSubmit: boolean;
  disableAiQaExtraction?: boolean;
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

const CSV_EXAMPLE_HEADERS = ['index', 'q', 'a', 'img', 'url', 'display'] as const;

const CSV_EXAMPLE_ROWS = [
  ['1', 'PRP術後多久可以碰水？', '24小時內避免碰水並依醫囑照護', 'IMG_PRP_001', 'https://example.com/prp', 'true'],
  ['2', '療程前需要注意什麼？', '請先告知用藥與過敏史', '', 'https://example.com/checklist', 'false'],
] as const;

const CSV_EXAMPLE_TEXT = [CSV_EXAMPLE_HEADERS, ...CSV_EXAMPLE_ROWS]
  .map((row) => row.join(','))
  .join('\n');

function downloadCsvExample() {
  downloadBlob(
    new Blob([`\uFEFF${CSV_EXAMPLE_TEXT}`], { type: 'text/csv;charset=utf-8' }),
    'qa-upload-example.csv',
  );
}

function CsvFormatExample() {
  return (
    <section className="qa-workspace-csv-example" aria-labelledby="qa-csv-example-title">
      <div className="qa-workspace-csv-example-header">
        <div className="qa-workspace-csv-example-title">
          <Table size={15} />
          <h4 id="qa-csv-example-title">CSV 格式範例</h4>
        </div>
        <button
          type="button"
          className="qa-workspace-csv-example-download"
          onClick={downloadCsvExample}
        >
          <Download size={14} />
          <span>下載 CSV 範例</span>
        </button>
      </div>
      <div className="qa-workspace-csv-example-table-wrap">
        <table className="qa-workspace-csv-example-table">
          <thead>
            <tr>
              {CSV_EXAMPLE_HEADERS.map((header) => (
                <th key={header}>{header}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {CSV_EXAMPLE_ROWS.map((row) => (
              <tr key={row[0]}>
                {row.map((cell, index) => (
                  <td key={`${row[0]}-${index}`}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
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
  disableAiQaExtraction = false,
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

  const extractionLabel = disableAiQaExtraction ? '開始上傳' : '開始 AI 擷取';
  const uploadLabel = isCsvOrXlsx ? '開始上傳' : extractionLabel;
  const textPlaceholder = disableAiQaExtraction
    ? '在此貼上文字內容，將直接儲存並建立索引。'
    : '在此貼上文章內容，AI 會自動分析並擷取問答對。';

  return (
    <div className="qa-doc-source-tab">
      <div className="qa-doc-mode-toggle" role="tablist">
        <button
          type="button"
          role="tab"
          className={`qa-doc-mode-button${mode === 'file' ? ' is-active' : ''}`}
          onClick={() => onModeChange('file')}
        >
          <FileText size={14} />
          <span>上傳檔案</span>
        </button>
        <button
          type="button"
          role="tab"
          className={`qa-doc-mode-button${mode === 'text' ? ' is-active' : ''}`}
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
            <div className="qa-workspace-upload-error-banner">
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
            <div key={`${item.file.name}-${index}`} className="qa-workspace-upload-file-item">
              <FileText size={16} className="qa-icon-dark-blue" />
              <span className="qa-workspace-upload-file-name">{item.file.name}</span>
              <span className="qa-workspace-upload-file-size">{formatFileSize(item.file.size)}</span>
              <div className="qa-workspace-file-actions">
                <button
                  type="button"
                  className="qa-workspace-qa-row-delete"
                  onClick={onRemoveFile}
                  title="移除"
                >
                  <X size={14} />
                </button>
              </div>
            </div>
          )}
          afterContent={<CsvFormatExample />}
        />
      )}

      {mode === 'text' && (
        <div className="qa-workspace-upload-file-body">
          <textarea
            className="qa-doc-text-input custom-scrollbar"
            placeholder={textPlaceholder}
            value={text}
            onChange={(event) => onTextChange(event.target.value)}
          />
          <div className="qa-doc-text-meta">
            <span className={text.length > MAX_TEXT_LENGTH ? 'is-over' : ''}>
              {text.length.toLocaleString()} / {MAX_TEXT_LENGTH.toLocaleString()} 字
            </span>
          </div>
          {error && (
            <div className="qa-workspace-upload-error-banner">
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}
          <div className="qa-workspace-qa-footer">
            <span className="qa-workspace-qa-count">
              {text.trim().length > 0 ? '1 段文字' : '0 段文字'}
            </span>
            <div className="qa-workspace-qa-footer-actions">
              <button type="button" className="qa-workspace-file-action-button" onClick={onClose}>
                取消
              </button>
              <button
                type="button"
                className="qa-workspace-file-action-button primary"
                disabled={!canSubmit}
                onClick={onStartExtraction}
              >
                {extractionLabel}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
