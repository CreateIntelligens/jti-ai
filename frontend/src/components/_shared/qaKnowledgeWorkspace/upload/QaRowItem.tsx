import { Image as ImageIcon, Loader2, Table, Trash2, X, XCircle } from 'lucide-react';

import ZoomableThumbnail from '../ZoomableThumbnail';
import type { QARow } from './types';

interface QaRowItemProps {
  index: number;
  row: QARow;
  previewUrl: string;
  visibilityHint: string;
  onUpdate: (updates: Partial<QARow>) => void;
  onRemove: () => void;
  onClearImage: () => void;
  onUploadImage: () => void;
  onChooseExisting: () => void;
  onPreviewImage: (url: string) => void;
}

export default function QaRowItem({
  index,
  row,
  previewUrl,
  visibilityHint,
  onUpdate,
  onRemove,
  onClearImage,
  onUploadImage,
  onChooseExisting,
  onPreviewImage,
}: QaRowItemProps) {
  const imageLabel = row.pendingImageName || row.img;
  const hasImage = Boolean(imageLabel);

  return (
    <div className="qa-workspace-qa-row">
      <span className="qa-workspace-qa-row-number">{index + 1}</span>
      <label className="qa-workspace-qa-row-visible" title={visibilityHint}>
        <input
          type="checkbox"
          className="qa-workspace-qa-row-visible-checkbox"
          checked={row.visible}
          onChange={(event) => onUpdate({ visible: event.target.checked })}
        />
      </label>
      <div className="qa-workspace-qa-row-fields">
        <input
          className="qa-workspace-qa-input"
          placeholder="問題 (Q)"
          value={row.q}
          onChange={(event) => onUpdate({ q: event.target.value })}
        />
        <div className="qa-workspace-qa-row-fields-inner">
          <textarea
            className="qa-workspace-qa-textarea qa-workspace-qa-textarea-flexible"
            placeholder="回答 (A)"
            value={row.a}
            onChange={(event) => onUpdate({ a: event.target.value })}
            rows={2}
          />
          <div className="qa-workspace-qa-row-image">
            {hasImage && (
              <div className="qa-workspace-qa-image-preview">
                {previewUrl ? (
                  <ZoomableThumbnail
                    src={previewUrl}
                    alt={imageLabel}
                    className="qa-workspace-qa-image-thumb"
                    onZoom={onPreviewImage}
                  />
                ) : (
                  <span className="qa-workspace-qa-image-name" title={imageLabel}>{imageLabel}</span>
                )}
                {row.imgStatus === 'uploading' && (
                  <Loader2 size={14} className="animate-spin" />
                )}
                {row.imgStatus === 'error' && (
                  <span title={row.imgError}><XCircle size={14} className="text-red-500" /></span>
                )}
                <button type="button" className="qa-workspace-qa-image-clear" onClick={onClearImage}>
                  <X size={10} />
                </button>
              </div>
            )}
            <div className={`qa-workspace-qa-image-actions${hasImage ? ' has-preview' : ''}`}>
              <button
                type="button"
                className="qa-workspace-qa-image-btn"
                onClick={onUploadImage}
                title="上傳圖片"
              >
                <ImageIcon size={14} />
                {!hasImage && '上傳'}
              </button>
              <button
                type="button"
                className="qa-workspace-qa-image-btn"
                onClick={onChooseExisting}
                title="選擇既有圖片"
              >
                <Table size={14} />
                {!hasImage && '既有'}
              </button>
            </div>
          </div>
        </div>
        <input
          className="qa-workspace-qa-input"
          placeholder="網址 (URL)"
          value={row.url || ''}
          onChange={(event) => onUpdate({ url: event.target.value })}
        />
      </div>
      <button
        type="button"
        className="qa-workspace-qa-row-delete"
        onClick={onRemove}
        title="移除"
      >
        <Trash2 size={14} />
      </button>
    </div>
  );
}
