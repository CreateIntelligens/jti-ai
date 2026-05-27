import { AlertCircle } from 'lucide-react';

import type { HciotLanguage } from '../../../../config/hciotTopics';
import type { HciotQaPair } from '../../../../services/api';
import QaEditPreview from './QaEditPreview';

interface DocumentToQaPreviewProps {
  language: HciotLanguage;
  isEn: boolean;
  qaPairs: HciotQaPair[];
  error: string | null;
  onChange: (pairs: HciotQaPair[]) => void;
  onReset: () => void;
  onImport: () => void;
}

export default function DocumentToQaPreview({
  language,
  qaPairs,
  error,
  onChange,
  onReset,
  onImport,
}: DocumentToQaPreviewProps) {
  return (
    <div className="hciot-upload-file-body">
      <QaEditPreview qaPairs={qaPairs} onChange={onChange} language={language} />
      {error && (
        <div className="hciot-upload-error-banner hciot-qa-preview-error">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}
      <div className="hciot-qa-footer">
        <span className="hciot-qa-count">
          {qaPairs.length} 組
        </span>
        <div className="hciot-qa-footer-actions">
          <button type="button" className="hciot-file-action-button" onClick={onReset}>
            放棄重新上傳
          </button>
          <button
            type="button"
            className="hciot-file-action-button primary"
            onClick={onImport}
            disabled={qaPairs.length === 0}
          >
            確認匯入
          </button>
        </div>
      </div>
    </div>
  );
}
