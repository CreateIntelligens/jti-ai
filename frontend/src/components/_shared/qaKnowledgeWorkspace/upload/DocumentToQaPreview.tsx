import { useRef, useState } from 'react';
import { AlertCircle, Plus } from 'lucide-react';

import type { QaLanguage } from '../../../../config/qaTopics';
import type { QaImage } from '../../../../services/api/_shared/qaKnowledge';
import { getQaImageUrl } from '../../../../utils/qaImage';
import ExistingImagePicker from '../explorer/ExistingImagePicker';
import ImageLightbox from '../ImageLightbox';
import { usePendingImageUrls } from '../imageUpload';
import QaRowItem from './QaRowItem';
import {
  applyExistingRowImage,
  clearRowImageState,
  createEmptyRow,
  type QARow,
} from './types';

const VISIBILITY_HINT = '勾選：顯示為預設問題。取消：仍會進知識庫,但不出現在按鈕列。';

interface DocumentToQaPreviewProps {
  language: QaLanguage;
  availableImages: QaImage[];
  qaPairs: QARow[];
  error: string | null;
  resolveImageUrl?: (imageId?: string) => string | null;
  onChange: (pairs: QARow[]) => void;
  onReset: () => void;
  onImport: () => void;
}

export default function DocumentToQaPreview({
  language,
  availableImages,
  qaPairs,
  error,
  resolveImageUrl = getQaImageUrl,
  onChange,
  onReset,
  onImport,
}: DocumentToQaPreviewProps) {
  const [pendingRowImageIndex, setPendingRowImageIndex] = useState<number | null>(null);
  const [pickerRowIndex, setPickerRowIndex] = useState<number | null>(null);
  const [previewImageUrl, setPreviewImageUrl] = useState<string | null>(null);
  const rowImageInputRef = useRef<HTMLInputElement>(null);
  const pendingUrls = usePendingImageUrls(qaPairs);

  const updateRow = (index: number, updates: Partial<QARow>) => {
    onChange(qaPairs.map((row, i) => (i === index ? { ...row, ...updates } : row)));
  };

  const removeRow = (index: number) => {
    onChange(qaPairs.filter((_, i) => i !== index));
  };

  const addRow = () => {
    onChange([...qaPairs, { ...createEmptyRow(), visible: false }]);
  };

  const handleRowImageSelect = (fileList: FileList | null) => {
    const file = fileList?.[0];
    if (!file?.type.startsWith('image/') || pendingRowImageIndex === null) return;

    const rowIndex = pendingRowImageIndex;
    setPendingRowImageIndex(null);
    updateRow(rowIndex, {
      img: '',
      pendingImageFile: file,
      pendingImageName: file.name,
      imgStatus: 'pending',
      imgError: undefined,
    });

    if (rowImageInputRef.current) rowImageInputRef.current.value = '';
  };

  return (
    <div className="qa-workspace-upload-qa-body">
      <ExistingImagePicker
        open={pickerRowIndex !== null}
        language={language}
        images={availableImages}
        selectedImageId={pickerRowIndex === null ? null : (qaPairs[pickerRowIndex]?.img || null)}
        onClose={() => setPickerRowIndex(null)}
        onSelect={(id) => {
          if (pickerRowIndex !== null) {
            updateRow(pickerRowIndex, applyExistingRowImage(qaPairs[pickerRowIndex], id));
            setPickerRowIndex(null);
          }
        }}
      />

      <ImageLightbox
        url={previewImageUrl}
        onClose={() => setPreviewImageUrl(null)}
      />

      <div className="qa-workspace-qa-preview-header">
        <h4 className="qa-workspace-qa-preview-title">
          擷取到 {qaPairs.length} 組問答對
        </h4>
        <p className="qa-workspace-qa-preview-subtitle">
          匯入後預設不顯示為快速問答按鈕（仍可透過 RAG 檢索）。若要設為預設問題請逐條勾選。
        </p>
      </div>

      <div className="qa-workspace-qa-rows custom-scrollbar">
        {qaPairs.map((row, index) => {
          const previewUrl = row.pendingImageFile
            ? pendingUrls.get(row.pendingImageFile) || ''
            : resolveImageUrl(row.img) || '';

          return (
            <QaRowItem
              key={index}
              index={index}
              row={row}
              previewUrl={previewUrl}
              visibilityHint={VISIBILITY_HINT}
              onUpdate={(updates) => updateRow(index, updates)}
              onRemove={() => removeRow(index)}
              onClearImage={() => updateRow(index, clearRowImageState(row))}
              onUploadImage={() => {
                setPendingRowImageIndex(index);
                rowImageInputRef.current?.click();
              }}
              onChooseExisting={() => setPickerRowIndex(index)}
              onPreviewImage={setPreviewImageUrl}
            />
          );
        })}
      </div>

      <input
        ref={rowImageInputRef}
        type="file"
        hidden
        accept="image/*"
        onChange={(event) => handleRowImageSelect(event.target.files)}
      />

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
