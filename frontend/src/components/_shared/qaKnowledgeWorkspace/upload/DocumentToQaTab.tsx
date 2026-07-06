import { useEffect, useRef, useState } from 'react';

import type { QaLanguage } from '../../../../config/qaTopics';
import { toErrorMessage } from '../../../../utils/errors';
import type { QaImage, QaPair } from '../../../../services/api/_shared/qaKnowledge';
import { createEmptyRow, type QARow } from './types';
import type { ResolvedUploadTopic } from './types';
import type { TopicLabels } from '../topicUtils';
import {
  extractUploadedImageId,
  rollbackUploadedImages,
  type DeleteImageHandler,
  type UploadedImageResult,
} from '../imageUpload';
import DocumentToQaPreview from './DocumentToQaPreview';
import DocumentToQaSourceForm from './DocumentToQaSourceForm';
import DocumentToQaStatusView from './DocumentToQaStatusView';
import type { QaWorkspaceApiClient } from '../QaKnowledgeWorkspace';
import {
  MAX_FILE_SIZE_BYTES,
  MAX_TEXT_LENGTH,
  SUPPORTED_EXTS,
  type DocFileItem,
  type DocumentSourceMode,
  type DocumentToQaStatus,
} from './documentToQaTypes';

interface DocumentToQaTabProps {
  open: boolean;
  language: QaLanguage;
  uploading: boolean;
  resolvedTopic: ResolvedUploadTopic | null;
  topicSelectionIncomplete: boolean;
  onClose: () => void;
  onUploadFile: (
    file: File,
    topicId: string | null,
    labels: TopicLabels | null,
    hiddenQuestions?: string[],
  ) => Promise<UploadFileResult>;
  onUploadComplete: (
    firstUploadedFileName: string | null,
    count: number,
    topicId?: string | null,
  ) => Promise<void>;
  api: QaWorkspaceApiClient;
  // Hide the HCIoT-only img/url columns in the CSV format example / download.
  disableImages?: boolean;
  availableImages: QaImage[];
  resolveImageUrl?: (imageId?: string) => string | null;
  onUploadImage: (file: File, imageId?: string) => Promise<UploadedImageResult>;
  onDeleteImage?: DeleteImageHandler;
}

type UploadFileResult = { name: string };
const CLOSE_AFTER_SUCCESS_MS = 1200;
const HIDDEN_DISPLAY_VALUES = new Set(['false', '0', '否', 'n']);

function fileExtension(file: File): string | undefined {
  return file.name.split('.').pop()?.toLowerCase();
}

function toHiddenPreviewRows(pairs: QaPair[]): QARow[] {
  // `display` may be absent in older CSV rows. Default to hidden, and honor it
  // when the CSV provides one.
  const rows = pairs.map((pair): QARow => ({
    ...createEmptyRow(),
    index: pair.index || '',
    q: pair.q,
    a: pair.a,
    img: pair.img || '',
    url: pair.url || '',
    imgStatus: pair.img ? 'done' : 'pending',
    visible: pair.display === undefined ? false : parseDisplayValue(pair.display),
  }));
  // Order the preview by the user-supplied index (blank/non-numeric last,
  // ties keep original order) so it matches the final stored order.
  const indexValue = (row: QARow): number => {
    const raw = (row.index ?? '').trim();
    const n = Number(raw);
    return raw !== '' && Number.isFinite(n) ? n : Infinity;
  };
  return rows
    .map((row, i) => ({ row, i }))
    .sort((a, b) => indexValue(a.row) - indexValue(b.row) || a.i - b.i)
    .map(({ row }) => row);
}

function parseDisplayValue(value: string | undefined): boolean {
  return value === undefined || !HIDDEN_DISPLAY_VALUES.has(value.trim().toLowerCase());
}

function getHiddenQuestions(rows: QARow[]): string[] {
  const hiddenQuestions = rows
    .filter((row) => !row.visible)
    .map((row) => row.q.trim())
    .filter(Boolean);
  return Array.from(new Set(hiddenQuestions));
}

function escapeCsvCell(value: string): string {
  return /[",\n\r]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

function buildQaCsv(rows: QARow[]): string {
  return [
    'index,q,a,img,url',
    ...rows.map(
      (row) =>
        `${escapeCsvCell(row.index || '')},${escapeCsvCell(row.q)},${escapeCsvCell(
          row.a,
        )},${escapeCsvCell(row.img || '')},${escapeCsvCell(row.url || '')}`,
    ),
  ].join('\n');
}

export default function DocumentToQaTab({
  open,
  language,
  uploading,
  resolvedTopic,
  topicSelectionIncomplete,
  onClose,
  onUploadFile,
  onUploadComplete,
  api,
  disableImages = false,
  availableImages,
  resolveImageUrl,
  onUploadImage,
  onDeleteImage,
}: DocumentToQaTabProps) {
  const isEn = language === 'en';

  const [mode, setMode] = useState<DocumentSourceMode>('file');
  const [file, setFile] = useState<DocFileItem | null>(null);
  const [text, setText] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [status, setStatus] = useState<DocumentToQaStatus>('idle');
  const [qaPairs, setQaPairs] = useState<QARow[]>([]);
  const [error, setError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const completeSingleFileUpload = async (result: UploadFileResult, topicId?: string | null) => {
    await onUploadComplete(result.name || null, result.name ? 1 : 0, topicId);
  };

  const closeAfterSuccess = () => {
    window.setTimeout(() => onClose(), CLOSE_AFTER_SUCCESS_MS);
  };

  const saveFileDirect = async (fileToSave: File) => {
    if (!resolvedTopic) return;
    setStatus('uploading');
    try {
      const res = await onUploadFile(
        fileToSave,
        resolvedTopic.fullTopicId,
        resolvedTopic.labels,
      );
      setStatus('success');
      await completeSingleFileUpload(res, resolvedTopic.fullTopicId);
      closeAfterSuccess();
    } catch (err: unknown) {
      setError(toErrorMessage(err));
      setStatus('error');
    }
  };

  useEffect(() => {
    if (open) {
      setMode('file');
      setFile(null);
      setText('');
      setStatus('idle');
      setQaPairs([]);
      setError(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }, [open]);

  const validateFile = (selectedFile: File): string | null => {
    const ext = fileExtension(selectedFile);
    if (!ext || !SUPPORTED_EXTS.includes(ext)) {
      return '不支援的檔案格式，僅支援 .csv, .xlsx, .docx, .txt, .md';
    }
    if (selectedFile.size > MAX_FILE_SIZE_BYTES) {
      return '檔案大小不可超過 5 MB';
    }
    return null;
  };

  const handleFileSelect = (fileList: FileList | null) => {
    setError(null);
    const selected = fileList?.[0];
    if (!selected) return;
    const validationError = validateFile(selected);
    if (validationError) {
      setError(validationError);
      return;
    }
    setFile({ file: selected });
  };

  const showPreviewRows = (rows: QARow[]) => {
    setQaPairs(rows);
    setStatus('preview');
  };

  const showParsedCsvPreview = async (csvText: string): Promise<boolean> => {
    try {
      const { parsed, qa_pairs: parsedPairs } = await api.parseQaCsvText(csvText);
      if (!parsed || parsedPairs.length === 0) {
        return false;
      }
      showPreviewRows(toHiddenPreviewRows(parsedPairs));
      return true;
    } catch {
      return false;
    }
  };

  const startExtraction = async () => {
    if (!resolvedTopic || topicSelectionIncomplete) {
      setError('請先選擇科別與主題。');
      return;
    }

    setError(null);

    if (mode === 'file') {
      if (!file) {
        setError('請先選擇檔案。');
        return;
      }

      const ext = fileExtension(file.file);
      if (ext === 'docx' || ext === 'txt' || ext === 'md') {
        await saveFileDirect(file.file);
        return;
      }

      if (ext === 'csv' || ext === 'xlsx') {
        if (ext === 'csv' && await showParsedCsvPreview(await file.file.text())) {
          return;
        }

        setStatus('uploading');
        try {
          const res = await onUploadFile(
            file.file,
            resolvedTopic.fullTopicId,
            resolvedTopic.labels,
          );
          setStatus('success');
          await completeSingleFileUpload(res, resolvedTopic.fullTopicId);
          closeAfterSuccess();
        } catch (err: unknown) {
          setError(toErrorMessage(err));
          setStatus('error');
        }
      }
      return;
    }

    const trimmed = text.trim();
    if (!trimmed) {
      setError('請輸入文字內容。');
      return;
    }
    if (trimmed.length > MAX_TEXT_LENGTH) {
      setError(`文字長度超過 ${MAX_TEXT_LENGTH} 字`);
      return;
    }

    setStatus('uploading');
    if (await showParsedCsvPreview(trimmed)) {
      return;
    }

    const mdFile = new File([trimmed], `pasted-${Date.now()}.md`, { type: 'text/markdown' });
    await saveFileDirect(mdFile);
  };

  /** Upload images staged on preview rows, returning rows with `img` filled in.
   * On failure, rolls back already-uploaded images and restores the original
   * pending state so the user can retry; returns null. */
  const uploadPendingRowImages = async (): Promise<QARow[] | null> => {
    const preparedRows = [...qaPairs];
    const uploadedImageIds: string[] = [];
    for (let i = 0; i < preparedRows.length; i++) {
      const row = preparedRows[i];
      if (!row.pendingImageFile) continue;
      try {
        const imageId = extractUploadedImageId(await onUploadImage(row.pendingImageFile));
        uploadedImageIds.push(imageId);
        preparedRows[i] = {
          ...row,
          img: imageId,
          pendingImageFile: undefined,
          pendingImageName: undefined,
          imgStatus: 'done',
          imgError: undefined,
        };
      } catch (err) {
        await rollbackUploadedImages(uploadedImageIds, onDeleteImage);
        const message = toErrorMessage(err);
        setQaPairs(qaPairs.map((original, idx) => (
          idx === i ? { ...original, imgStatus: 'error', imgError: message } : original
        )));
        setError(message);
        setStatus('preview');
        return null;
      }
    }
    return preparedRows;
  };

  const handleImport = async () => {
    if (qaPairs.length === 0) {
      setError('問答列表不可為空。');
      return;
    }
    setError(null);
    setStatus('importing');
    const preparedRows = await uploadPendingRowImages();
    if (!preparedRows) return;
    setQaPairs(preparedRows);
    const hiddenQuestions = getHiddenQuestions(preparedRows);
    try {
      if (!resolvedTopic) {
        setError('請先選擇科別與主題。');
        setStatus('preview');
        return;
      }
      const csv = buildQaCsv(preparedRows);
      const csvFile = new File([csv], `pasted-${Date.now()}.csv`, { type: 'text/csv' });
      const res = await onUploadFile(csvFile, resolvedTopic.fullTopicId, resolvedTopic.labels, hiddenQuestions);
      setStatus('success');
      await completeSingleFileUpload(res, resolvedTopic.fullTopicId);
      closeAfterSuccess();
    } catch (err) {
      setError(toErrorMessage(err));
      setStatus('preview');
    }
  };

  const handleReset = () => {
    setFile(null);
    setText('');
    setQaPairs([]);
    setError(null);
    setStatus('idle');
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const isUploading = status === 'uploading' || status === 'importing';

  if (isUploading || status === 'success' || status === 'error') {
    return (
      <DocumentToQaStatusView
        status={status}
        isEn={isEn}
        error={error}
        qaPairCount={qaPairs.length}
        onReset={handleReset}
      />
    );
  }

  if (status === 'preview') {
    return (
      <DocumentToQaPreview
        language={language}
        availableImages={availableImages}
        qaPairs={qaPairs}
        error={error}
        resolveImageUrl={resolveImageUrl}
        onChange={setQaPairs}
        onReset={handleReset}
        onImport={() => { void handleImport(); }}
      />
    );
  }

  const fileItems = file ? [file] : [];
  const canSubmit = !topicSelectionIncomplete && resolvedTopic !== null && (
    mode === 'file' ? !!file : text.trim().length > 0
  ) && !uploading;

  return (
    <DocumentToQaSourceForm
      language={language}
      isEn={isEn}
      mode={mode}
      fileItems={fileItems}
      text={text}
      error={error}
      dragOver={dragOver}
      fileInputRef={fileInputRef}
      canSubmit={canSubmit}
      disableImages={disableImages}
      onModeChange={(nextMode) => {
        setMode(nextMode);
        setError(null);
      }}
      onTextChange={(nextText) => {
        setText(nextText);
        setError(null);
      }}
      onDragOverChange={setDragOver}
      onFileSelect={handleFileSelect}
      onRemoveFile={() => {
        setFile(null);
        setError(null);
      }}
      onStartExtraction={() => { void startExtraction(); }}
      onClose={onClose}
    />
  );
}
