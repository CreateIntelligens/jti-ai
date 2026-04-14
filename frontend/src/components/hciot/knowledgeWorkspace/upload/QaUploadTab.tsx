import { useEffect, useRef, useState } from 'react';
import { Image as ImageIcon, Loader2, Plus, Table, Trash2, Upload, X, XCircle } from 'lucide-react';

import type { HciotLanguage } from '../../../../config/hciotTopics';
import type { HciotImage } from '../../../../services/api/hciot';
import { getHciotImageUrl } from '../../../../utils/hciotImage';
import ExistingImagePicker from '../explorer/ExistingImagePicker';
import {
  applyExistingRowImage,
  buildCsvBlob,
  clearRowImageState,
  createEmptyRow,
  type QARow,
  type ResolvedUploadTopic,
} from './types';
import {
  extractUploadedImageId,
  rollbackUploadedImages,
  usePendingImageUrls,
  type DeleteImageHandler,
  type UploadedImageResult,
} from '../imageUpload';

interface QaUploadTabProps {
  open: boolean;
  language: HciotLanguage;
  uploading: boolean;
  availableImages: HciotImage[];
  resolvedTopic: ResolvedUploadTopic | null;
  hasTopicSelection: boolean;
  onClose: () => void;
  onSubmitQA: (file: File, topicId: string, labels: ResolvedUploadTopic['labels']) => Promise<void>;
  onUploadImage: (file: File, imageId?: string) => Promise<UploadedImageResult>;
  onDeleteImage?: DeleteImageHandler;
}

interface QaRowItemProps {
  index: number;
  row: QARow;
  language: HciotLanguage;
  previewUrl: string;
  onUpdate: (updates: Partial<QARow>) => void;
  onRemove: () => void;
  onClearImage: () => void;
  onUploadImage: () => void;
  onChooseExisting: () => void;
}

function QaRowItem({
  index,
  row,
  language,
  previewUrl,
  onUpdate,
  onRemove,
  onClearImage,
  onUploadImage,
  onChooseExisting,
}: QaRowItemProps) {
  const imageLabel = row.pendingImageName || row.img;
  const hasImage = Boolean(imageLabel);

  return (
    <div className="hciot-qa-row">
      <span className="hciot-qa-row-number">{index + 1}</span>
      <div className="hciot-qa-row-fields">
        <input
          className="hciot-qa-input"
          placeholder={language === 'zh' ? '問題 (Q)' : 'Question (Q)'}
          value={row.q}
          onChange={(event) => onUpdate({ q: event.target.value })}
        />
        <div className="hciot-qa-row-fields-inner">
          <textarea
            className="hciot-qa-textarea hciot-qa-textarea-flexible"
            placeholder={language === 'zh' ? '回答 (A)' : 'Answer (A)'}
            value={row.a}
            onChange={(event) => onUpdate({ a: event.target.value })}
            rows={2}
          />
          <div className="hciot-qa-row-image">
            {hasImage && (
              <div className="hciot-qa-image-preview">
                {previewUrl ? (
                  <img src={previewUrl} alt={imageLabel} className="hciot-qa-image-thumb" />
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
            <div style={{ display: 'flex', gap: '6px', marginTop: hasImage ? '4px' : 0 }}>
              <button
                type="button"
                className="hciot-qa-image-btn"
                onClick={onUploadImage}
                title={language === 'zh' ? '上傳圖片' : 'Upload Image'}
              >
                <ImageIcon size={14} />
                {!hasImage && (language === 'zh' ? '上傳' : 'Upload')}
              </button>
              <button
                type="button"
                className="hciot-qa-image-btn"
                onClick={onChooseExisting}
                title={language === 'zh' ? '選擇既有圖片' : 'Choose Existing Image'}
              >
                <Table size={14} />
                {!hasImage && (language === 'zh' ? '既有' : 'Existing')}
              </button>
            </div>
          </div>
        </div>
      </div>
      <button
        type="button"
        className="hciot-qa-row-delete"
        onClick={onRemove}
        title={language === 'zh' ? '移除' : 'Remove'}
      >
        <Trash2 size={14} />
      </button>
    </div>
  );
}

export default function QaUploadTab({
  open,
  language,
  uploading,
  availableImages,
  resolvedTopic,
  hasTopicSelection,
  onClose,
  onSubmitQA,
  onUploadImage,
  onDeleteImage,
}: QaUploadTabProps) {
  const [rows, setRows] = useState<QARow[]>([createEmptyRow()]);
  const [uploadingLocal, setUploadingLocal] = useState(false);
  const [pendingRowImageIndex, setPendingRowImageIndex] = useState<number | null>(null);
  const [pickerRowIndex, setPickerRowIndex] = useState<number | null>(null);
  const rowImageInputRef = useRef<HTMLInputElement>(null);
  const pendingUrls = usePendingImageUrls(rows);

  useEffect(() => {
    if (open) {
      setRows([createEmptyRow()]);
      setUploadingLocal(false);
      setPendingRowImageIndex(null);
      setPickerRowIndex(null);
    }
  }, [open]);

  const validRows = rows.filter((row) => row.q.trim());
  const canSubmitQA = validRows.length > 0 && hasTopicSelection && !uploadingLocal && !uploading;

  const updateRow = (index: number, updates: Partial<QARow>) => {
    setRows((prev) => prev.map((row, i) => (i === index ? { ...row, ...updates } : row)));
  };

  const removeRow = (index: number) => {
    setRows((prev) => {
      const next = prev.filter((_, i) => i !== index);
      return next.length > 0 ? next : [createEmptyRow()];
    });
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

  const handleSubmit = async () => {
    if (!validRows.length || !resolvedTopic) return;

    setUploadingLocal(true);
    const originalRows = rows.map((row) => ({ ...row }));
    const uploadedImageIds: string[] = [];
    let failedIndex: number | null = null;
    let failedMsg: string | undefined;
    let stage: 'images' | 'submit' = 'images';

    try {
      const preparedRows = [...originalRows];
      for (let i = 0; i < preparedRows.length; i++) {
        const row = preparedRows[i];
        if (!row.q.trim() || !row.pendingImageFile) continue;

        updateRow(i, { imgStatus: 'uploading', imgError: undefined });

        try {
          const imageId = extractUploadedImageId(await onUploadImage(row.pendingImageFile));
          uploadedImageIds.push(imageId);

          const updates: Partial<QARow> = {
            img: imageId,
            pendingImageFile: undefined,
            pendingImageName: undefined,
            imgStatus: 'done',
            imgError: undefined,
          };
          preparedRows[i] = { ...preparedRows[i], ...updates };
          updateRow(i, updates);
        } catch (error: any) {
          failedIndex = i;
          failedMsg = error?.message || String(error);
          throw error;
        }
      }

      stage = 'submit';
      const prefix = (resolvedTopic.fullTopicId.split('/').pop() || resolvedTopic.fullTopicId)
        .toUpperCase()
        .replace(/-/g, '_');
      const blob = buildCsvBlob(preparedRows.filter((row) => row.q.trim()));
      const file = new File([blob], `${prefix.toLowerCase()}_qa_${Date.now()}.csv`, { type: 'text/csv' });
      await onSubmitQA(file, resolvedTopic.fullTopicId, resolvedTopic.labels);
    } catch (error) {
      if (stage === 'images') {
        await rollbackUploadedImages(uploadedImageIds, onDeleteImage);
        if (failedIndex !== null) {
          updateRow(failedIndex, { imgStatus: 'error', imgError: failedMsg });
        }
      }
      alert(error instanceof Error ? error.message : String(error));
    } finally {
      setUploadingLocal(false);
    }
  };

  return (
    <>
      <ExistingImagePicker
        open={pickerRowIndex !== null}
        language={language}
        images={availableImages}
        selectedImageId={pickerRowIndex === null ? null : (rows[pickerRowIndex]?.img || null)}
        onClose={() => setPickerRowIndex(null)}
        onSelect={(id) => {
          if (pickerRowIndex !== null) {
            updateRow(pickerRowIndex, applyExistingRowImage(rows[pickerRowIndex], id));
            setPickerRowIndex(null);
          }
        }}
      />

      <div className="hciot-upload-qa-body">
        <div className="hciot-qa-rows custom-scrollbar">
          {rows.map((row, index) => (
            <QaRowItem
              key={index}
              index={index}
              row={row}
              language={language}
              previewUrl={row.pendingImageFile ? pendingUrls.get(row.pendingImageFile) || '' : getHciotImageUrl(row.img) || ''}
              onUpdate={(updates) => updateRow(index, updates)}
              onRemove={() => removeRow(index)}
              onClearImage={() => updateRow(index, clearRowImageState(row))}
              onUploadImage={() => {
                setPendingRowImageIndex(index);
                rowImageInputRef.current?.click();
              }}
              onChooseExisting={() => setPickerRowIndex(index)}
            />
          ))}
        </div>

        <input
          ref={rowImageInputRef}
          type="file"
          hidden
          accept="image/*"
          onChange={(event) => handleRowImageSelect(event.target.files)}
        />

        <button
          type="button"
          className="hciot-qa-add-row"
          onClick={() => setRows((prev) => [...prev, createEmptyRow()])}
        >
          <Plus size={14} />
          {language === 'zh' ? '新增一題' : 'Add row'}
        </button>

        <div className="hciot-qa-footer">
          <span className="hciot-qa-count">
            {validRows.length} {language === 'zh' ? '題有效' : 'valid Q(s)'}
          </span>
          <div className="hciot-qa-footer-actions">
            <button type="button" className="hciot-file-action-button" onClick={onClose}>
              {language === 'zh' ? '取消' : 'Cancel'}
            </button>
            <button
              type="button"
              className="hciot-file-action-button primary"
              disabled={!canSubmitQA}
              onClick={() => { void handleSubmit(); }}
            >
              <Upload size={14} />
              {uploadingLocal || uploading
                ? (language === 'zh' ? '上傳中...' : 'Uploading...')
                : (language === 'zh' ? '上傳' : 'Upload')}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
