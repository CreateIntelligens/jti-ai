import { AlertCircle, Loader2 } from 'lucide-react';

import type { DocumentToQaStatus } from './documentToQaTypes';

interface DocumentToQaStatusViewProps {
  status: Extract<DocumentToQaStatus, 'uploading' | 'extracting' | 'importing' | 'success' | 'error'>;
  isEn: boolean;
  error: string | null;
  qaPairCount: number;
  onReset: () => void;
}

function progressTitle(status: DocumentToQaStatus, _isEn: boolean): string {
  if (status === 'importing') {
    return '問答匯入中...';
  }
  if (status === 'uploading') {
    return '上傳中...';
  }
  return 'AI 分析中，正在擷取問答對...';
}

export default function DocumentToQaStatusView({
  status,
  isEn: _isEn,
  error,
  qaPairCount,
  onReset,
}: DocumentToQaStatusViewProps) {
  if (status === 'success') {
    return (
      <div className="qa-workspace-upload-file-body">
        <div className="hciot-doc-success-step">
          <div className="hciot-success-badge">✓</div>
          <h4 className="hciot-success-title">匯入成功！</h4>
          <p className="hciot-success-subtitle">已成功匯入 {qaPairCount} 組問答。</p>
        </div>
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="qa-workspace-upload-file-body">
        <div className="hciot-doc-error-step">
          <AlertCircle size={36} className="hciot-error-icon" />
          <h4 className="hciot-error-title">處理時發生錯誤</h4>
          <p className="hciot-error-subtitle">{error}</p>
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
      <div className="hciot-doc-progress-step">
        <Loader2 size={36} className="hciot-spinner" />
        <h4 className="hciot-progress-title">
          {progressTitle(status, _isEn)}
        </h4>
        <p className="hciot-progress-subtitle">通常需要 10-30 秒，視內容長度而定。</p>
      </div>
    </div>
  );
}
