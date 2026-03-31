import { useEffect, useMemo, useRef, useState } from 'react';
import { Plus, Trash2, Upload, X } from 'lucide-react';

import type { HciotLanguage } from '../../../config/hciotTopics';
import type { HciotTopicCategory } from '../../../services/api/hciot';
import { NEW_VALUE, slugify, sortByLabel, type TopicLabels } from './shared';

type Tab = 'file' | 'qa';

interface QARow {
  q: string;
  a: string;
}

interface UploadDialogProps {
  open: boolean;
  language: HciotLanguage;
  categories: HciotTopicCategory[];
  uploading: boolean;
  onClose: () => void;
  onUploadFiles: (files: File[], topicId: string | null, labels: TopicLabels | null) => Promise<void>;
  onSubmitQA: (file: File, topicId: string, labels: TopicLabels) => Promise<void>;
}

function createEmptyRow(): QARow {
  return { q: '', a: '' };
}

function buildCsvBlob(rows: QARow[], topicPrefix: string): Blob {
  const lines = ['index,q,a,img'];
  rows.forEach((row, i) => {
    const index = `${topicPrefix}_${String(i + 1).padStart(3, '0')}`;
    const q = row.q.replace(/"/g, '""');
    const a = row.a.replace(/"/g, '""');
    lines.push(`${index},"${q}","${a}",`);
  });
  return new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
}

const DEFAULT_CATEGORY = 'other';

function useTopicSelection(categories: HciotTopicCategory[], language: HciotLanguage, open: boolean) {
  const [categoryId, setCategoryId] = useState(DEFAULT_CATEGORY);
  const [topicId, setTopicId] = useState('');
  const [newCategoryZh, setNewCategoryZh] = useState('');
  const [newCategoryEn, setNewCategoryEn] = useState('');
  const [newTopicZh, setNewTopicZh] = useState('');
  const [newTopicEn, setNewTopicEn] = useState('');

  useEffect(() => {
    if (open) {
      setCategoryId(DEFAULT_CATEGORY);
      setTopicId('');
      setNewCategoryZh('');
      setNewCategoryEn('');
      setNewTopicZh('');
      setNewTopicEn('');
    }
  }, [open]);

  const sortedCategories = useMemo(
    () => categories.slice().sort((a, b) => sortByLabel(a.labels[language], b.labels[language])),
    [categories, language],
  );

  const currentCategory = useMemo(
    () => (categoryId && categoryId !== NEW_VALUE ? categories.find((c) => c.id === categoryId) : null),
    [categories, categoryId],
  );

  const sortedTopics = useMemo(() => {
    if (!currentCategory) return [];
    return currentCategory.topics.slice().sort((a, b) => sortByLabel(a.labels[language], b.labels[language]));
  }, [currentCategory, language]);

  const handleCategoryChange = (value: string) => {
    setCategoryId(value);
    setTopicId('');
    setNewTopicZh('');
    setNewTopicEn('');
    if (value !== NEW_VALUE) {
      setNewCategoryZh('');
      setNewCategoryEn('');
    }
  };

  const handleTopicChange = (value: string) => {
    setTopicId(value);
    if (value !== NEW_VALUE) {
      setNewTopicZh('');
      setNewTopicEn('');
    }
  };

  const resolveIds = (): { fullTopicId: string; labels: TopicLabels } | null => {
    const effectiveCatId = categoryId === NEW_VALUE
      ? slugify(newCategoryEn || newCategoryZh)
      : categoryId;
    if (!effectiveCatId) return null;

    const effectiveTopicSlug = topicId === NEW_VALUE
      ? slugify(newTopicEn || newTopicZh)
      : (topicId ? topicId.split('/').pop() || topicId : '');

    const fullTopicId = effectiveTopicSlug
      ? `${effectiveCatId}/${effectiveTopicSlug}`
      : effectiveCatId;

    const catLabels = categoryId === NEW_VALUE
      ? { zh: newCategoryZh.trim(), en: newCategoryEn.trim() }
      : { zh: currentCategory?.labels.zh || '', en: currentCategory?.labels.en || '' };

    const existingTopic = currentCategory?.topics.find((item) => item.id === topicId);
    const topicMatch = topicId === NEW_VALUE
      ? { zh: newTopicZh.trim(), en: newTopicEn.trim() }
      : { zh: existingTopic?.labels.zh || '', en: existingTopic?.labels.en || '' };

    return {
      fullTopicId,
      labels: {
        categoryLabelZh: catLabels.zh,
        categoryLabelEn: catLabels.en,
        topicLabelZh: topicMatch.zh,
        topicLabelEn: topicMatch.en,
      },
    };
  };

  return {
    categoryId, topicId,
    newCategoryZh, newCategoryEn, newTopicZh, newTopicEn,
    setNewCategoryZh, setNewCategoryEn, setNewTopicZh, setNewTopicEn,
    sortedCategories, sortedTopics,
    handleCategoryChange, handleTopicChange,
    resolveIds,
  };
}

export default function UploadDialog({
  open,
  language,
  categories,
  uploading,
  onClose,
  onUploadFiles,
  onSubmitQA,
}: UploadDialogProps) {
  const [tab, setTab] = useState<Tab>('file');
  const [rows, setRows] = useState<QARow[]>([createEmptyRow()]);
  const [dragOver, setDragOver] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const topic = useTopicSelection(categories, language, open);

  useEffect(() => {
    if (open) {
      setTab('file');
      setRows([createEmptyRow()]);
      setSelectedFiles([]);
      setDragOver(false);
    }
  }, [open]);

  const validRows = rows.filter((r) => r.q.trim());

  const canSubmitFile = selectedFiles.length > 0 && !uploading;
  const canSubmitQA = validRows.length > 0 && (topic.categoryId || topic.newCategoryZh || topic.newCategoryEn) && !uploading;

  const updateRow = (index: number, field: keyof QARow, value: string) => {
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, [field]: value } : r)));
  };

  const removeRow = (index: number) => {
    setRows((prev) => {
      const next = prev.filter((_, i) => i !== index);
      return next.length > 0 ? next : [createEmptyRow()];
    });
  };

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files.length > 0) {
      setSelectedFiles((prev) => [...prev, ...Array.from(e.dataTransfer.files)]);
    }
  };

  const handleFileSelect = (fileList: FileList | null) => {
    if (fileList && fileList.length > 0) {
      setSelectedFiles((prev) => [...prev, ...Array.from(fileList)]);
    }
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const removeFile = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleUploadFiles = async () => {
    if (!selectedFiles.length) return;
    const resolved = topic.resolveIds();
    await onUploadFiles(
      selectedFiles,
      resolved?.fullTopicId || null,
      resolved?.labels || null,
    );
  };

  const handleSubmitQA = async () => {
    if (!validRows.length) return;
    const resolved = topic.resolveIds();
    if (!resolved) return;

    const prefix = (resolved.fullTopicId.split('/').pop() || resolved.fullTopicId)
      .toUpperCase().replace(/-/g, '_');
    const blob = buildCsvBlob(validRows, prefix);
    const fileName = `${prefix.toLowerCase()}_qa_${Date.now()}.csv`;
    const file = new File([blob], fileName, { type: 'text/csv' });
    await onSubmitQA(file, resolved.fullTopicId, resolved.labels);
  };

  if (!open) return null;

  return (
    <div className="hciot-qa-overlay" onClick={onClose}>
      <div className="hciot-qa-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="hciot-qa-header">
          <h3>{language === 'zh' ? '新增知識' : 'Add Knowledge'}</h3>
          <button type="button" className="hciot-qa-close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="hciot-upload-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            className={`hciot-upload-tab${tab === 'file' ? ' is-active' : ''}`}
            onClick={() => setTab('file')}
            aria-selected={tab === 'file'}
          >
            <Upload size={14} />
            {language === 'zh' ? '上傳檔案' : 'Upload Files'}
          </button>
          <button
            type="button"
            role="tab"
            className={`hciot-upload-tab${tab === 'qa' ? ' is-active' : ''}`}
            onClick={() => setTab('qa')}
            aria-selected={tab === 'qa'}
          >
            <Plus size={14} />
            {language === 'zh' ? '手動輸入 Q&A' : 'Manual Q&A'}
          </button>
        </div>

        {/* Shared: topic selector */}
        <div className="hciot-qa-topic-section">
          <label className="hciot-qa-topic-label">
            {language === 'zh' ? '指定科別 / 主題（可選）' : 'Category / Topic (optional)'}
          </label>
          <div className="hciot-qa-selectors">
            <select
              className="hciot-file-select"
              value={topic.categoryId}
              onChange={(e) => topic.handleCategoryChange(e.target.value)}
            >
              <option value="">{language === 'zh' ? '— 不指定 —' : '— None —'}</option>
              {topic.sortedCategories.map((cat) => (
                <option key={cat.id} value={cat.id}>{cat.labels[language]}</option>
              ))}
              <option value={NEW_VALUE}>{language === 'zh' ? '＋ 新增科別' : '+ New category'}</option>
            </select>

            <span className="hciot-file-path-separator">/</span>

            <select
              className="hciot-file-select"
              value={topic.topicId}
              onChange={(e) => topic.handleTopicChange(e.target.value)}
              disabled={!topic.categoryId || topic.categoryId === NEW_VALUE}
            >
              <option value="">{language === 'zh' ? '— 不指定 —' : '— None —'}</option>
              {topic.sortedTopics.map((t) => (
                <option key={t.id} value={t.id}>{t.labels[language]}</option>
              ))}
              {topic.categoryId && topic.categoryId !== NEW_VALUE ? (
                <option value={NEW_VALUE}>{language === 'zh' ? '＋ 新增主題' : '+ New topic'}</option>
              ) : null}
            </select>
          </div>

          {topic.categoryId === NEW_VALUE ? (
            <div className="hciot-qa-new-fields">
              <input
                className="hciot-file-input"
                placeholder={language === 'zh' ? '新科別中文名稱' : 'New category (zh)'}
                value={topic.newCategoryZh}
                onChange={(e) => topic.setNewCategoryZh(e.target.value)}
              />
              <input
                className="hciot-file-input"
                placeholder={language === 'zh' ? '新科別英文名稱' : 'New category (en)'}
                value={topic.newCategoryEn}
                onChange={(e) => topic.setNewCategoryEn(e.target.value)}
              />
            </div>
          ) : null}

          {topic.topicId === NEW_VALUE ? (
            <div className="hciot-qa-new-fields">
              <input
                className="hciot-file-input"
                placeholder={language === 'zh' ? '新主題中文名稱' : 'New topic (zh)'}
                value={topic.newTopicZh}
                onChange={(e) => topic.setNewTopicZh(e.target.value)}
              />
              <input
                className="hciot-file-input"
                placeholder={language === 'zh' ? '新主題英文名稱' : 'New topic (en)'}
                value={topic.newTopicEn}
                onChange={(e) => topic.setNewTopicEn(e.target.value)}
              />
            </div>
          ) : null}
        </div>

        {/* Tab: Upload Files */}
        {tab === 'file' ? (
          <div className="hciot-upload-file-body">
            <div
              className={`hciot-upload-dropzone${dragOver ? ' is-drag-over' : ''}`}
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleFileDrop}
            >
              <Upload size={24} />
              <p>{language === 'zh' ? '點擊或拖放檔案' : 'Click or drop files here'}</p>
              <span>{language === 'zh' ? '支援 CSV、PDF、TXT、Word 等' : 'CSV, PDF, TXT, Word, etc.'}</span>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              hidden
              multiple
              onChange={(e) => handleFileSelect(e.target.files)}
            />

            {selectedFiles.length > 0 ? (
              <div className="hciot-upload-file-list">
                {selectedFiles.map((file, i) => (
                  <div key={`${file.name}-${i}`} className="hciot-upload-file-item">
                    <span className="hciot-upload-file-name">{file.name}</span>
                    <span className="hciot-upload-file-size">
                      {file.size > 1024 ? `${(file.size / 1024).toFixed(1)} KB` : `${file.size} B`}
                    </span>
                    <button
                      type="button"
                      className="hciot-qa-row-delete"
                      onClick={() => removeFile(i)}
                    >
                      <X size={14} />
                    </button>
                  </div>
                ))}
              </div>
            ) : null}

            <div className="hciot-qa-footer">
              <span className="hciot-qa-count">
                {selectedFiles.length} {language === 'zh' ? '個檔案' : 'file(s)'}
              </span>
              <div className="hciot-qa-footer-actions">
                <button type="button" className="hciot-file-action-button" onClick={onClose}>
                  {language === 'zh' ? '取消' : 'Cancel'}
                </button>
                <button
                  type="button"
                  className="hciot-file-action-button primary"
                  disabled={!canSubmitFile}
                  onClick={() => { void handleUploadFiles(); }}
                >
                  <Upload size={14} />
                  {uploading
                    ? (language === 'zh' ? '上傳中...' : 'Uploading...')
                    : (language === 'zh' ? '上傳' : 'Upload')}
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {/* Tab: Manual Q&A */}
        {tab === 'qa' ? (
          <div className="hciot-upload-qa-body">
            <div className="hciot-qa-rows">
              {rows.map((row, index) => (
                <div key={index} className="hciot-qa-row">
                  <span className="hciot-qa-row-number">{index + 1}</span>
                  <div className="hciot-qa-row-fields">
                    <input
                      className="hciot-qa-input"
                      placeholder={language === 'zh' ? '問題 (Q)' : 'Question (Q)'}
                      value={row.q}
                      onChange={(e) => updateRow(index, 'q', e.target.value)}
                    />
                    <textarea
                      className="hciot-qa-textarea"
                      placeholder={language === 'zh' ? '回答 (A)' : 'Answer (A)'}
                      value={row.a}
                      onChange={(e) => updateRow(index, 'a', e.target.value)}
                      rows={2}
                    />
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
              ))}
            </div>

            <button type="button" className="hciot-qa-add-row" onClick={() => setRows((prev) => [...prev, createEmptyRow()])}>
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
                  onClick={() => { void handleSubmitQA(); }}
                >
                  <Upload size={14} />
                  {uploading
                    ? (language === 'zh' ? '上傳中...' : 'Uploading...')
                    : (language === 'zh' ? '產生 CSV 並上傳' : 'Generate CSV & Upload')}
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
