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
    <div className="hciot-qa-row">
      <span className="hciot-qa-row-number">{index + 1}</span>
      <label className="hciot-qa-row-visible" title={visibilityHint}>
        <input
          type="checkbox"
          className="hciot-qa-row-visible-checkbox"
          checked={row.visible}
          onChange={(event) => onUpdate({ visible: event.target.checked })}
        />
      </label>
      <div className="hciot-qa-row-fields">
        <input
          className="hciot-qa-input"
          placeholder="問題 (Q)"
          value={row.q}
          onChange={(event) => onUpdate({ q: event.target.value })}
        />
        <div className="hciot-qa-row-fields-inner">
          <textarea
            className="hciot-qa-textarea hciot-qa-textarea-flexible"
            placeholder="回答 (A)"
            value={row.a}
            onChange={(event) => onUpdate({ a: event.target.value })}
            rows={2}
          />
          <div className="hciot-qa-row-image">
            {hasImage && (
              <div className="hciot-qa-image-preview">
                {previewUrl ? (
                  <ZoomableThumbnail
                    src={previewUrl}
                    alt={imageLabel}
                    className="hciot-qa-image-thumb"
                    onZoom={onPreviewImage}
                  />
                ) : (
                  <span className="hciot-qa-image-name" title={imageLabel}>{imageLabel}</span>
                )}
                {row.imgStatus === 'uploading' && (
                  <Loader2 size={14} className="animate-spin" />
                )}
                {row.imgStatus === 'error' && (
                  <span title={row.imgError}><XCircle size={14} className="text-red-500" /></span>
                )}
                <button type="button" className="hciot-qa-image-clear" onClick={onClearImage}>
                  <X size={10} />
                </button>
              </div>
            )}
            <div className={`hciot-qa-image-actions${hasImage ? ' has-preview' : ''}`}>
              <button
                type="button"
                className="hciot-qa-image-btn"
                onClick={onUploadImage}
                title="上傳圖片"
              >
                <ImageIcon size={14} />
                {!hasImage && '上傳'}
              </button>
              <button
                type="button"
                className="hciot-qa-image-btn"
                onClick={onChooseExisting}
                title="選擇既有圖片"
              >
                <Table size={14} />
                {!hasImage && '既有'}
              </button>
            </div>
          </div>
        </div>
      </div>
      <button
        type="button"
        className="hciot-qa-row-delete"
        onClick={onRemove}
        title="移除"
      >
        <Trash2 size={14} />
      </button>
    </div>
  );
}
