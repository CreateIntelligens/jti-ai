import { AlertCircle, Loader2 } from 'lucide-react';

import type { DocumentToQaStatus } from './documentToQaTypes';

interface DocumentToQaStatusViewProps {
  status: Extract<DocumentToQaStatus, 'uploading' | 'extracting' | 'importing' | 'success' | 'error'>;
  isEn: boolean;
  error: string | null;
  qaPairCount: number;
  /** When true, the content was saved directly (chunked by RAG) rather than
   * going through AI Q&A extraction — adjust the wording accordingly. */
  directSave?: boolean;
  onReset: () => void;
}

function progressTitle(status: DocumentToQaStatus, directSave: boolean): string {
  if (status === 'importing') {
    return '問答匯入中...';
  }
  if (status === 'uploading') {
    return directSave ? '儲存並建立索引中...' : '上傳中...';
  }
  return 'AI 分析中，正在擷取問答對...';
}

export default function DocumentToQaStatusView({
  status,
  isEn: _isEn,
  error,
  qaPairCount,
  directSave = false,
  onReset,
}: DocumentToQaStatusViewProps) {
  if (status === 'success') {
    return (
      <div className="qa-workspace-upload-file-body">
        <div className="qa-doc-success-step">
          <div className="qa-success-badge">✓</div>
          <h4 className="qa-success-title">{directSave ? '儲存成功！' : '匯入成功！'}</h4>
          <p className="qa-success-subtitle">
            {directSave ? '內容已儲存並建立索引。' : `已成功匯入 ${qaPairCount} 組問答。`}
          </p>
        </div>
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="qa-workspace-upload-file-body">
        <div className="qa-doc-error-step">
          <AlertCircle size={36} className="qa-error-icon" />
          <h4 className="qa-error-title">處理時發生錯誤</h4>
          <p className="qa-error-subtitle">{error}</p>
          <div className="qa-workspace-qa-footer-actions">
            <button type="button" className="qa-workspace-file-action-button" onClick={onReset}>
              重新開始
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="qa-workspace-upload-file-body">
      <div className="qa-doc-progress-step">
        <Loader2 size={36} className="qa-spinner" />
        <h4 className="qa-progress-title">
          {progressTitle(status, directSave)}
        </h4>
        <p className="qa-progress-subtitle">
          {directSave ? '請稍候，正在處理內容。' : '通常需要 10-30 秒，視內容長度而定。'}
        </p>
      </div>
    </div>
  );
}
