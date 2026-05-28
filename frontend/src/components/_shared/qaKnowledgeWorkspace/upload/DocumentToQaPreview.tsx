import { AlertCircle, Plus } from 'lucide-react';

import QaRowItem from './QaRowItem';
import { clearRowImageState, createEmptyRow, type QARow } from './types';

const VISIBILITY_HINT = '勾選：顯示為預設問題。取消：仍會進知識庫,但不出現在按鈕列。';
const noop = () => undefined;

interface DocumentToQaPreviewProps {
  qaPairs: QARow[];
  error: string | null;
  onChange: (pairs: QARow[]) => void;
  onReset: () => void;
  onImport: () => void;
}

export default function DocumentToQaPreview({
  qaPairs,
  error,
  onChange,
  onReset,
  onImport,
}: DocumentToQaPreviewProps) {
  const updateRow = (index: number, updates: Partial<QARow>) => {
    onChange(qaPairs.map((row, i) => (i === index ? { ...row, ...updates } : row)));
  };

  const removeRow = (index: number) => {
    onChange(qaPairs.filter((_, i) => i !== index));
  };

  const addRow = () => {
    onChange([...qaPairs, { ...createEmptyRow(), visible: false }]);
  };

  return (
    <div className="qa-workspace-upload-qa-body">
      <div className="qa-workspace-qa-preview-header">
        <h4 className="qa-workspace-qa-preview-title">
          擷取到 {qaPairs.length} 組問答對
        </h4>
        <p className="qa-workspace-qa-preview-subtitle">
          匯入後預設不顯示為快速問答按鈕（仍可透過 RAG 檢索）。若要設為預設問題請逐條勾選。
        </p>
      </div>

      <div className="qa-workspace-qa-rows custom-scrollbar">
        {qaPairs.map((row, index) => (
          <QaRowItem
            key={index}
            index={index}
            row={row}
            previewUrl=""
            visibilityHint={VISIBILITY_HINT}
            onUpdate={(updates) => updateRow(index, updates)}
            onRemove={() => removeRow(index)}
            onClearImage={() => updateRow(index, clearRowImageState(row))}
            onUploadImage={noop}
            onChooseExisting={noop}
            onPreviewImage={noop}
          />
        ))}
      </div>

      <button type="button" className="qa-workspace-qa-add-row" onClick={addRow}>
        <Plus size={14} />
        新增一題
      </button>

      {error && (
        <div className="qa-workspace-upload-error-banner qa-workspace-qa-preview-error">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      <div className="qa-workspace-qa-footer">
        <span className="qa-workspace-qa-count">{qaPairs.length} 組</span>
        <div className="qa-workspace-qa-footer-actions">
          <button type="button" className="qa-workspace-file-action-button" onClick={onReset}>
            放棄重新上傳
          </button>
          <button
            type="button"
            className="qa-workspace-file-action-button primary"
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
