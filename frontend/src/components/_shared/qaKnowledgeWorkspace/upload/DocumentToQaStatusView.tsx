import { AlertCircle, Loader2 } from 'lucide-react';

import type { DocumentToQaStatus } from './documentToQaTypes';

interface DocumentToQaStatusViewProps {
  status: Extract<DocumentToQaStatus, 'uploading' | 'importing' | 'success' | 'error'>;
  isEn: boolean;
  error: string | null;
  qaPairCount: number;
  onReset: () => void;
}

function progressTitle(status: DocumentToQaStatus): string {
  if (status === 'importing') {
    return '問答匯入中...';
  }
  return '儲存並建立索引中...';
}

export default function DocumentToQaStatusView({
  status,
  isEn: _isEn,
  error,
  qaPairCount,
  onReset,
}: DocumentToQaStatusViewProps) {
  const hasQaPairs = qaPairCount > 0;

  if (status === 'success') {
    return (
      <div className="qa-workspace-upload-file-body">
        <div className="qa-doc-success-step">
          <div className="qa-success-badge">✓</div>
          <h4 className="qa-success-title">{hasQaPairs ? '匯入成功！' : '儲存成功！'}</h4>
          <p className="qa-success-subtitle">
            {hasQaPairs ? `已成功匯入 ${qaPairCount} 組問答。` : '內容已儲存並建立索引。'}
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
          {progressTitle(status)}
        </h4>
        <p className="qa-progress-subtitle">
          請稍候，正在處理內容。
        </p>
      </div>
    </div>
  );
}
