import { useEffect, useRef, useState } from 'react';

import type { HciotLanguage } from '../../../../config/hciotTopics';
import { toErrorMessage } from '../../../../utils/errors';
import type { HciotQaPair } from '../../../../services/api/hciot';
import { createEmptyRow, type QARow } from './types';
import type { ResolvedUploadTopic } from './types';
import type { TopicLabels } from '../topicUtils';
import DocumentToQaPreview from './DocumentToQaPreview';
import DocumentToQaSourceForm from './DocumentToQaSourceForm';
import DocumentToQaStatusView from './DocumentToQaStatusView';
import type { QaWorkspaceApiClient } from '../QaKnowledgeWorkspace';
import {
  MAX_FILE_SIZE_BYTES,
  MAX_TEXT_LENGTH,
  POLLING_INTERVAL_MS,
  SUPPORTED_EXTS,
  TIMEOUT_MS,
  type DocFileItem,
  type DocumentSourceMode,
  type DocumentToQaStatus,
} from './documentToQaTypes';

interface DocumentToQaTabProps {
  open: boolean;
  language: HciotLanguage;
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
}

type PendingAiSource = { kind: 'file'; file: File } | { kind: 'text'; text: string };
type UploadFileResult = { name: string };

function fileExtension(file: File): string | undefined {
  return file.name.split('.').pop()?.toLowerCase();
}

function toHiddenPreviewRows(pairs: HciotQaPair[]): QARow[] {
  return pairs.map((pair) => ({
    ...createEmptyRow(),
    q: pair.q,
    a: pair.a,
    img: pair.img || '',
    url: pair.url || '',
    imgStatus: pair.img ? 'done' : 'pending',
    visible: false,
  }));
}

function getHiddenQuestions(rows: QARow[]): string[] {
  const hiddenQuestions = rows
    .filter((row) => !row.visible)
    .map((row) => row.q.trim())
    .filter(Boolean);
  return Array.from(new Set(hiddenQuestions));
}

function toPlainQaPairs(rows: QARow[]): HciotQaPair[] {
  return rows.map(({ q, a, img, url }) => {
    const pair: HciotQaPair = { q, a };
    if (img) pair.img = img;
    if (url) pair.url = url;
    return pair;
  });
}

function escapeCsvCell(value: string): string {
  return /[",\n\r]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

function buildQaCsv(rows: QARow[]): string {
  return [
    'q,a,img,url',
    ...rows.map(
      (row) =>
        `${escapeCsvCell(row.q)},${escapeCsvCell(row.a)},${escapeCsvCell(
          row.img || '',
        )},${escapeCsvCell(row.url || '')}`,
    ),
  ].join('\n');
}

function isUnrecognizedFormatError(error: unknown): boolean {
  try {
    const parsed = JSON.parse(toErrorMessage(error)) as {
      error_code?: string;
      detail?: { error_code?: string };
    };
    return parsed.error_code === 'unrecognized_format'
      || parsed.detail?.error_code === 'unrecognized_format';
  } catch {
    return false;
  }
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
}: DocumentToQaTabProps) {
  const isEn = language === 'en';

  const [mode, setMode] = useState<DocumentSourceMode>('file');
  const [file, setFile] = useState<DocFileItem | null>(null);
  const [text, setText] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [status, setStatus] = useState<DocumentToQaStatus>('idle');
  const [jobId, setJobId] = useState<string | null>(null);
  const [qaPairs, setQaPairs] = useState<QARow[]>([]);
  const [error, setError] = useState<string | null>(null);

  const pollingTimerRef = useRef<number | null>(null);
  const startTimeRef = useRef<number>(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const completeSingleFileUpload = async (result: UploadFileResult, topicId?: string | null) => {
    await onUploadComplete(result.name || null, result.name ? 1 : 0, topicId);
  };

  useEffect(() => {
    if (open) {
      setMode('file');
      setFile(null);
      setText('');
      setStatus('idle');
      setJobId(null);
      setQaPairs([]);
      setError(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }, [open]);

  useEffect(() => () => {
    if (pollingTimerRef.current !== null) {
      window.clearInterval(pollingTimerRef.current);
    }
  }, []);

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

  const stopPolling = () => {
    if (pollingTimerRef.current !== null) {
      window.clearInterval(pollingTimerRef.current);
      pollingTimerRef.current = null;
    }
  };

  const startPolling = (id: string) => {
    if (pollingTimerRef.current !== null) {
      window.clearInterval(pollingTimerRef.current);
    }
    pollingTimerRef.current = window.setInterval(async () => {
      try {
        if (Date.now() - startTimeRef.current > TIMEOUT_MS) {
          stopPolling();
          setError('分析逾時，請稍後再試。');
          setStatus('error');
          return;
        }
        const res = await api.getQaExtractJob(id);
        if (res.status === 'done' && res.qa_pairs) {
          stopPolling();
          setQaPairs(toHiddenPreviewRows(res.qa_pairs));
          setStatus('preview');
        } else if (res.status === 'failed') {
          stopPolling();
          setError(res.error || '問答擷取失敗。');
          setStatus('error');
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    }, POLLING_INTERVAL_MS);
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
        await startAiExtraction({ kind: 'file', file: file.file });
        return;
      }

      if (ext === 'csv' || ext === 'xlsx') {
        setStatus('uploading');
        try {
          const res = await onUploadFile(
            file.file,
            resolvedTopic.fullTopicId,
            resolvedTopic.labels,
          );
          setStatus('success');
          await completeSingleFileUpload(res, resolvedTopic.fullTopicId);
          window.setTimeout(() => onClose(), 1200);
        } catch (err: unknown) {
          if (isUnrecognizedFormatError(err)) {
            await startAiExtraction({ kind: 'file', file: file.file });
            return;
          }
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
    try {
      const { parsed, qa_pairs } = await api.parseQaCsvText(trimmed);
      if (parsed && qa_pairs.length > 0) {
        setJobId(null);
        setQaPairs(toHiddenPreviewRows(qa_pairs));
        setStatus('preview');
        return;
      }
    } catch {
      // Fall through to AI extraction when the parse probe fails.
    }
    await startAiExtraction({ kind: 'text', text: trimmed });
  };

  const startAiExtraction = async (source: PendingAiSource) => {
    if (!resolvedTopic) return;
    setStatus('uploading');

    const topicParts = resolvedTopic.fullTopicId.split('/');
    const categoryId = topicParts[0];
    const topicId = resolvedTopic.fullTopicId;
    const categoryLabel = resolvedTopic.labels.categoryLabel;
    const topicLabel = resolvedTopic.labels.topicLabel;

    try {
      const res = await api.createQaExtractJob(
        language,
        source.kind === 'file' ? { file: source.file } : { text: source.text },
        categoryId,
        topicId,
        categoryLabel,
        topicLabel,
      );
      setJobId(res.job_id);
      setStatus('extracting');
      startTimeRef.current = Date.now();
      startPolling(res.job_id);
    } catch (err) {
      setError(toErrorMessage(err));
      setStatus('error');
    }
  };

  const handleImport = async () => {
    if (qaPairs.length === 0) {
      setError('問答列表不可為空。');
      return;
    }
    setError(null);
    setStatus('importing');
    const hiddenQuestions = getHiddenQuestions(qaPairs);
    const plainPairs = toPlainQaPairs(qaPairs);
    try {
      if (jobId) {
        const res = await api.importQaExtractJob(jobId, language, plainPairs, hiddenQuestions);
        setStatus('success');
        await onUploadComplete(res.filename, res.imported_count, res.topic_id ?? resolvedTopic?.fullTopicId ?? null);
      } else {
        if (!resolvedTopic) {
          setError('請先選擇科別與主題。');
          setStatus('preview');
          return;
        }
        const csv = buildQaCsv(qaPairs);
        const csvFile = new File([csv], `pasted-${Date.now()}.csv`, { type: 'text/csv' });
        const res = await onUploadFile(csvFile, resolvedTopic.fullTopicId, resolvedTopic.labels, hiddenQuestions);
        setStatus('success');
        await completeSingleFileUpload(res, resolvedTopic.fullTopicId);
      }
      window.setTimeout(() => onClose(), 1200);
    } catch (err) {
      setError(toErrorMessage(err));
      setStatus('preview');
    }
  };

  const handleReset = () => {
    stopPolling();
    setFile(null);
    setText('');
    setJobId(null);
    setQaPairs([]);
    setError(null);
    setStatus('idle');
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const isUploading = status === 'uploading' || status === 'extracting' || status === 'importing';

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
        qaPairs={qaPairs}
        error={error}
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
