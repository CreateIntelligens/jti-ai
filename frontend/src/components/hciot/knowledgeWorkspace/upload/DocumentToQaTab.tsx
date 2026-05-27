import { useEffect, useRef, useState } from 'react';

import type { HciotLanguage } from '../../../../config/hciotTopics';
import { toErrorMessage } from '../../../../utils/errors';
import * as api from '../../../../services/api';
import type { HciotQaPair } from '../../../../services/api';
import type { ResolvedUploadTopic } from './types';
import type { TopicLabels } from '../topicUtils';
import DocumentToQaPreview from './DocumentToQaPreview';
import DocumentToQaSourceForm from './DocumentToQaSourceForm';
import DocumentToQaStatusView from './DocumentToQaStatusView';
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
  ) => Promise<{ name: string }>;
  onUploadComplete: (firstUploadedFileName: string | null, count: number) => Promise<void>;
}

function fileExtension(file: File): string | undefined {
  return file.name.split('.').pop()?.toLowerCase();
}

function splitCsvLine(line: string): string[] {
  const cells: string[] = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"') {
        if (line[i + 1] === '"') { current += '"'; i++; }
        else { inQuotes = false; }
      } else { current += ch; }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ',') {
      cells.push(current);
      current = '';
    } else {
      current += ch;
    }
  }
  cells.push(current);
  return cells.map((c) => c.trim());
}

function parseQaPairsFromCsvText(raw: string): HciotQaPair[] | null {
  const cleaned = raw.replace(/^﻿/, '').trim();
  if (!cleaned) return null;
  const lines = cleaned.split(/\r?\n/).filter((line) => line.trim().length > 0);
  if (lines.length < 2) return null;
  const header = splitCsvLine(lines[0]).map((h) => h.toLowerCase());
  const qIdx = header.indexOf('q');
  const aIdx = header.indexOf('a');
  if (qIdx < 0 || aIdx < 0) return null;
  const pairs: HciotQaPair[] = [];
  for (let i = 1; i < lines.length; i++) {
    const cells = splitCsvLine(lines[i]);
    const q = (cells[qIdx] || '').trim();
    const a = (cells[aIdx] || '').trim();
    if (q && a) pairs.push({ q, a });
  }
  return pairs.length > 0 ? pairs : null;
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
}: DocumentToQaTabProps) {
  const isEn = language === 'en';

  const [mode, setMode] = useState<DocumentSourceMode>('file');
  const [file, setFile] = useState<DocFileItem | null>(null);
  const [text, setText] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [status, setStatus] = useState<DocumentToQaStatus>('idle');
  const [jobId, setJobId] = useState<string | null>(null);
  const [qaPairs, setQaPairs] = useState<HciotQaPair[]>([]);
  const [error, setError] = useState<string | null>(null);
  type PendingAiSource = { kind: 'file'; file: File } | { kind: 'text'; text: string };

  const pollingTimerRef = useRef<number | null>(null);
  const startTimeRef = useRef<number>(0);
const fileInputRef = useRef<HTMLInputElement>(null);

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
          setQaPairs(res.qa_pairs);
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
          await onUploadComplete(res.name, 1);
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

    const parsedPairs = parseQaPairsFromCsvText(trimmed);
    if (parsedPairs) {
      setJobId(null);
      setQaPairs(parsedPairs);
      setStatus('preview');
      return;
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
    try {
      if (jobId) {
        const res = await api.importQaExtractJob(jobId, language, qaPairs);
        setStatus('success');
        await onUploadComplete(res.filename, res.imported_count);
      } else {
        if (!resolvedTopic) {
          setError('請先選擇科別與主題。');
          setStatus('preview');
          return;
        }
        const escape = (v: string) => /[",\n\r]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
        const csv = ['q,a', ...qaPairs.map((p) => `${escape(p.q)},${escape(p.a)}`)].join('\n');
        const csvFile = new File([csv], `pasted-${Date.now()}.csv`, { type: 'text/csv' });
        const res = await onUploadFile(csvFile, resolvedTopic.fullTopicId, resolvedTopic.labels);
        setStatus('success');
        await onUploadComplete(res.name, 1);
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
        language={language}
        isEn={isEn}
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
