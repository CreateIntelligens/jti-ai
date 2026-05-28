import { useEffect, useRef, useState } from 'react';
import { Plus, Upload } from 'lucide-react';

import type { HciotLanguage } from '../../../../config/hciotTopics';
import type { HciotImage } from '../../../../services/api/hciot';
import { toErrorMessage } from '../../../../utils/errors';
import { getHciotImageUrl } from '../../../../utils/hciotImage';
import ExistingImagePicker from '../explorer/ExistingImagePicker';
import ImageLightbox from '../ImageLightbox';
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
import QaRowItem from './QaRowItem';

interface QaUploadTabProps {
  open: boolean;
  language: HciotLanguage;
  uploading: boolean;
  availableImages: HciotImage[];
  resolvedTopic: ResolvedUploadTopic | null;
  hasTopicSelection: boolean;
  onClose: () => void;
  onSubmitQA: (
    file: File,
    topicId: string,
    labels: ResolvedUploadTopic['labels'],
    hiddenQuestions: string[],
  ) => Promise<{ name: string; uploaded_count: number }>;

  onUploadComplete: (firstUploadedFileName: string | null, count: number) => Promise<void>;
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
  onUploadComplete,
  onUploadImage,
  onDeleteImage,
}: QaUploadTabProps) {
  const [rows, setRows] = useState<QARow[]>([createEmptyRow()]);
  const [uploadingLocal, setUploadingLocal] = useState(false);
  const [pendingRowImageIndex, setPendingRowImageIndex] = useState<number | null>(null);
  const [pickerRowIndex, setPickerRowIndex] = useState<number | null>(null);
  const [previewImageUrl, setPreviewImageUrl] = useState<string | null>(null);
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

  const visibilityHint = language === 'en'
    ? 'Checked: shown as a preset question. Unchecked: hidden from the chips but still added to the knowledge base.'
    : '勾選：顯示為預設問題按鈕。取消：不顯示在按鈕列，但仍會進知識庫。';

  const hasQuestion = (row: QARow) => row.q.trim().length > 0;
  const validRows = rows.filter(hasQuestion);
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
    let submitStage: 'images' | 'submit' = 'images';

    try {
      const preparedRows = [...originalRows];
      for (let i = 0; i < preparedRows.length; i++) {
        const row = preparedRows[i];
        if (!hasQuestion(row) || !row.pendingImageFile) continue;

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
        } catch (error) {
          failedIndex = i;
          failedMsg = toErrorMessage(error);
          throw error;
        }
      }

      submitStage = 'submit';
      const submittedRows = preparedRows.filter(hasQuestion);
      // Question text is the identity key. Match the backend's CSV extraction
      // (which strips each `q`), so a trimmed text is what lands in
      // hidden_questions.
      const hiddenQuestions = Array.from(
        new Set(
          submittedRows
            .filter((row) => !row.visible)
            .map((row) => row.q.trim()),
        ),
      );
      const prefix = (resolvedTopic.fullTopicId.split('/').pop() || resolvedTopic.fullTopicId)
        .toUpperCase()
        .replace(/-/g, '_');
      const blob = buildCsvBlob(submittedRows);
      const file = new File([blob], `${prefix.toLowerCase()}_qa_${Date.now()}.csv`, { type: 'text/csv' });
      const result = await onSubmitQA(file, resolvedTopic.fullTopicId, resolvedTopic.labels, hiddenQuestions);
      await onUploadComplete(result.name, result.uploaded_count);
    } catch (error) {
      if (submitStage === 'images') {
        await rollbackUploadedImages(uploadedImageIds, onDeleteImage);
        if (failedIndex !== null) {
          updateRow(failedIndex, { imgStatus: 'error', imgError: failedMsg });
        }
      }
      alert(toErrorMessage(error));
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

      <ImageLightbox
        url={previewImageUrl}
        onClose={() => setPreviewImageUrl(null)}
      />

      <div className="qa-workspace-upload-qa-body">
        <div className="qa-workspace-qa-rows custom-scrollbar">
          {rows.map((row, index) => {
            const previewUrl = row.pendingImageFile
              ? pendingUrls.get(row.pendingImageFile) || ''
              : getHciotImageUrl(row.img) || '';

            return (
              <QaRowItem
                key={index}
                index={index}
                row={row}
                previewUrl={previewUrl}
                visibilityHint={visibilityHint}
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

        <button
          type="button"
          className="qa-workspace-qa-add-row"
          onClick={() => setRows((prev) => [...prev, createEmptyRow()])}
        >
          <Plus size={14} />
          新增一題
        </button>

        <div className="qa-workspace-qa-footer">
          <span className="qa-workspace-qa-count">
            {validRows.length} 題有效
          </span>
          <div className="qa-workspace-qa-footer-actions">
            <button type="button" className="qa-workspace-file-action-button" onClick={onClose}>
              取消
            </button>
            <button
              type="button"
              className="qa-workspace-file-action-button primary"
              disabled={!canSubmitQA}
              onClick={() => { void handleSubmit(); }}
            >
              <Upload size={14} />
              {uploadingLocal || uploading ? '上傳中...' : '上傳'}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
