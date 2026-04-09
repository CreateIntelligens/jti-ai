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
    setRows((previous) => previous.map((row, rowIndex) => (
      rowIndex === index ? { ...row, ...updates } : row
    )));
  };

  const removeRow = (index: number) => {
    setRows((previous) => {
      const nextRows = previous.filter((_, rowIndex) => rowIndex !== index);
      return nextRows.length > 0 ? nextRows : [createEmptyRow()];
    });
  };

  const handleRowImageSelect = (fileList: FileList | null) => {
    if (!fileList?.length || pendingRowImageIndex === null) {
      return;
    }
    const file = fileList[0];
    if (!file.type.startsWith('image/')) {
      return;
    }

    const rowIndex = pendingRowImageIndex;
    setPendingRowImageIndex(null);
    setRows((previous) => previous.map((row, index) => index === rowIndex ? {
      ...row,
      img: '',
      pendingImageFile: file,
      pendingImageName: file.name,
      imgStatus: 'pending',
      imgError: undefined,
    } : row));

    if (rowImageInputRef.current) {
      rowImageInputRef.current.value = '';
    }
  };

  const handleSelectExistingImage = (imageId: string) => {
    if (pickerRowIndex === null) {
      return;
    }

    const rowIndex = pickerRowIndex;
    setPickerRowIndex(null);
    setRows((previous) => previous.map((row, index) => (
      index === rowIndex ? applyExistingRowImage(row, imageId) : row
    )));
  };

  const handleSubmit = async () => {
    if (!validRows.length || !resolvedTopic) {
      return;
    }

    setUploadingLocal(true);
    const originalRows = rows.map((row) => ({ ...row }));
    const uploadedImageIds: string[] = [];
    let imageUploadFailedIndex: number | null = null;
    let imageUploadFailedMessage: string | undefined;
    let stage: 'images' | 'submit' = 'images';

    try {
      const preparedRows = [...originalRows];
      for (const [index, row] of preparedRows.entries()) {
        if (!row.q.trim() || !row.pendingImageFile) {
          continue;
        }

        updateRow(index, { imgStatus: 'uploading', imgError: undefined });

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
          Object.assign(preparedRows[index], updates);
          updateRow(index, updates);
        } catch (error: any) {
          imageUploadFailedIndex = index;
          imageUploadFailedMessage = error?.message || String(error);
          throw error;
        }
      }

      stage = 'submit';
      const prefix = (resolvedTopic.fullTopicId.split('/').pop() || resolvedTopic.fullTopicId)
        .toUpperCase()
        .replace(/-/g, '_');
      const blob = buildCsvBlob(preparedRows.filter((row) => row.q.trim()), prefix);
      const file = new File([blob], `${prefix.toLowerCase()}_qa_${Date.now()}.csv`, { type: 'text/csv' });
      await onSubmitQA(file, resolvedTopic.fullTopicId, resolvedTopic.labels);
    } catch (error) {
      if (stage === 'images') {
        await rollbackUploadedImages(uploadedImageIds, onDeleteImage);
        setRows(originalRows.map((row, index) => index === imageUploadFailedIndex ? {
          ...row,
          imgStatus: 'error',
          imgError: imageUploadFailedMessage,
        } : row));
      }
      console.error('Failed to submit HCIoT Q&A:', error);
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
        onSelect={handleSelectExistingImage}
      />

      <div className="hciot-upload-qa-body">
        <div className="hciot-qa-rows">
          {rows.map((row, index) => {
            const imageLabel = row.pendingImageName || row.img;
            const hasImage = Boolean(imageLabel);
            const previewUrl = row.pendingImageFile
              ? pendingUrls.get(row.pendingImageFile) || ''
              : getHciotImageUrl(row.img) || '';

            return (
              <div key={index} className="hciot-qa-row">
                <span className="hciot-qa-row-number">{index + 1}</span>
                <div className="hciot-qa-row-fields">
                  <input
                    className="hciot-qa-input"
                    placeholder={language === 'zh' ? '問題 (Q)' : 'Question (Q)'}
                    value={row.q}
                    onChange={(event) => updateRow(index, { q: event.target.value })}
                  />
                  <textarea
                    className="hciot-qa-textarea"
                    placeholder={language === 'zh' ? '回答 (A)' : 'Answer (A)'}
                    value={row.a}
                    onChange={(event) => updateRow(index, { a: event.target.value })}
                    rows={2}
                  />
                </div>
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
                      <button
                        type="button"
                        className="hciot-qa-image-clear"
                        onClick={() => setRows((previous) => previous.map((item, itemIndex) => (
                          itemIndex === index ? clearRowImageState(item) : item
                        )))}
                      >
                        <X size={10} />
                      </button>
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: '6px', marginTop: hasImage ? '4px' : 0 }}>
                    <button
                      type="button"
                      className="hciot-qa-image-btn"
                      onClick={() => {
                        setPendingRowImageIndex(index);
                        rowImageInputRef.current?.click();
                      }}
                      title={language === 'zh' ? '上傳圖片' : 'Upload Image'}
                    >
                      <ImageIcon size={14} />
                      {!hasImage ? (language === 'zh' ? '上傳' : 'Upload') : null}
                    </button>
                    <button
                      type="button"
                      className="hciot-qa-image-btn"
                      onClick={() => setPickerRowIndex(index)}
                      title={language === 'zh' ? '選擇既有圖片' : 'Choose Existing Image'}
                    >
                      <Table size={14} />
                      {!hasImage ? (language === 'zh' ? '既有' : 'Existing') : null}
                    </button>
                  </div>
                </div>
                <button
                  type="button"
                  className="hciot-qa-row-delete"
                  onClick={() => removeRow(index)}
                  title={language === 'zh' ? '移除' : 'Remove'}
                >
                  <Trash2 size={14} />
                </button>
              </div>
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

        <button
          type="button"
          className="hciot-qa-add-row"
          onClick={() => setRows((previous) => [...previous, createEmptyRow()])}
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
