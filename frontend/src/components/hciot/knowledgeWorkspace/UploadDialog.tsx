import { useEffect, useMemo, useRef, useState } from 'react';
import { Plus, Trash2, Upload, X, Table, FileText, FileType, Image as ImageIcon, File as FileIcon, Loader2, CheckCircle2, XCircle, AlertCircle } from 'lucide-react';

import type { HciotLanguage } from '../../../config/hciotTopics';
import type { HciotTopicCategory } from '../../../services/api/hciot';
import { NEW_VALUE, slugify, sortByLabel, type TopicLabels } from './shared';

type Tab = 'file' | 'qa' | 'image';
type FileStatus = 'pending' | 'uploading' | 'done' | 'error';

interface QARow {
  q: string;
  a: string;
  img?: string;
  imgStatus?: FileStatus;
  imgError?: string;
}

interface FileItem {
  file: File;
  status: FileStatus;
  error?: string;
  isDuplicate?: boolean;
}

interface ImageItem {
  file: File;
  imageId: string;
  status: FileStatus;
  error?: string;
}

interface UploadDialogProps {
  open: boolean;
  language: HciotLanguage;
  categories: HciotTopicCategory[];
  uploading: boolean;
  onClose: () => void;
  onUploadFile: (file: File, topicId: string | null, labels: TopicLabels | null) => Promise<{ name: string }>;
  onUploadComplete: (firstUploadedFileName: string | null, count: number) => Promise<void>;
  onSubmitQA: (file: File, topicId: string, labels: TopicLabels) => Promise<void>;
  onUploadImage: (file: File, imageId?: string) => Promise<any>;
  onUploadImageComplete: (count: number) => Promise<void>;
}

function createEmptyRow(): QARow {
  return { q: '', a: '', img: '', imgStatus: 'pending' };
}

function buildCsvBlob(rows: QARow[], topicPrefix: string): Blob {
  const lines = ['index,q,a,img'];
  rows.forEach((row, i) => {
    const index = `${topicPrefix}_${String(i + 1).padStart(3, '0')}`;
    const q = row.q.replace(/"/g, '""');
    const a = row.a.replace(/"/g, '""');
    const img = (row.img || '').replace(/"/g, '""');
    lines.push(`${index},"${q}","${a}","${img}"`);
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

/**
 * Shared layout component for the different upload tabs (files and images).
 * This reduces redundancy by unifying the dropzone, file list container, and footer.
 */
interface UploadTabBodyProps {
  language: HciotLanguage;
  dragOver: boolean;
  setDragOver: (over: boolean) => void;
  onDrop: (e: React.DragEvent) => void;
  onSelect: (fileList: FileList | null) => void;
  inputRef: React.RefObject<HTMLInputElement | null>;
  accept?: string;
  items: any[];
  renderItem: (item: any, index: number) => React.ReactNode;
  isUploading: boolean;
  disabled: boolean;
  onUpload: () => void;
  onClose: () => void;
  dropLabelZh: string;
  dropLabelEn: string;
  dropSubZh: string;
  dropSubEn: string;
  countZh: string;
  countEn: string;
  listStyle?: React.CSSProperties;
}

function UploadTabBody({
  language, dragOver, setDragOver, onDrop, onSelect, inputRef, accept,
  items, renderItem, isUploading, disabled, onUpload, onClose,
  dropLabelZh, dropLabelEn, dropSubZh, dropSubEn, countZh, countEn,
  listStyle,
}: UploadTabBodyProps) {
  return (
    <div className="hciot-upload-file-body">
      <div
        className={`hciot-upload-dropzone${dragOver ? ' is-drag-over' : ''}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
      >
        <Upload size={24} />
        <p>{language === 'zh' ? dropLabelZh : dropLabelEn}</p>
        <span>{language === 'zh' ? dropSubZh : dropSubEn}</span>
      </div>
      <input
        ref={inputRef}
        type="file"
        hidden
        multiple
        accept={accept}
        onChange={(e) => onSelect(e.target.files)}
      />

      {items.length > 0 && (
        <div className="hciot-upload-file-list" style={listStyle}>
          {items.map((item, i) => renderItem(item, i))}
        </div>
      )}

      <div className="hciot-qa-footer">
        <span className="hciot-qa-count">
          {items.length} {language === 'zh' ? countZh : countEn}
        </span>
        <div className="hciot-qa-footer-actions">
          <button type="button" className="hciot-file-action-button" onClick={onClose}>
            {language === 'zh' ? '取消' : 'Cancel'}
          </button>
          <button
            type="button"
            className="hciot-file-action-button primary"
            disabled={disabled}
            onClick={onUpload}
          >
            <Upload size={14} />
            {isUploading
              ? (language === 'zh' ? '上傳中...' : 'Uploading...')
              : (language === 'zh' ? '上傳' : 'Upload')}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function UploadDialog({
  open,
  language,
  categories,
  uploading,
  onClose,
  onUploadFile,
  onUploadComplete,
  onSubmitQA,
  onUploadImage,
  onUploadImageComplete,
}: UploadDialogProps) {
  const [tab, setTab] = useState<Tab>('file');
  const [rows, setRows] = useState<QARow[]>([createEmptyRow()]);
  const [dragOver, setDragOver] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<FileItem[]>([]);
  const [selectedImages, setSelectedImages] = useState<ImageItem[]>([]);
  const [uploadingLocal, setUploadingLocal] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const rowImageInputRef = useRef<HTMLInputElement>(null);
  const [pendingRowImageIndex, setPendingRowImageIndex] = useState<number | null>(null);

  const topic = useTopicSelection(categories, language, open);

  useEffect(() => {
    if (open) {
      setTab('file');
      setRows([createEmptyRow()]);
      setSelectedFiles([]);
      setSelectedImages([]);
      setUploadingLocal(false);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  const validRows = rows.filter((r) => r.q.trim());
  const canSubmitFile = selectedFiles.some(f => f.status === 'pending' || f.status === 'error') && !uploadingLocal && !uploading;
  const canSubmitQA = validRows.length > 0 && (topic.categoryId || topic.newCategoryZh || topic.newCategoryEn) && !uploadingLocal && !uploading;
  const canSubmitImage = selectedImages.some(f => f.status === 'pending' || f.status === 'error') && !uploadingLocal;

  const updateRow = (index: number, field: keyof QARow, value: string) => {
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, [field]: value } : r)));
  };

  const removeRow = (index: number) => {
    setRows((prev) => {
      const next = prev.filter((_, i) => i !== index);
      return next.length > 0 ? next : [createEmptyRow()];
    });
  };

  const handleFileSelect = (fileList: FileList | null) => {
    if (!fileList?.length) return;
    const newFiles = Array.from(fileList).map(f => ({ file: f, status: 'pending' as const, isDuplicate: false }));
    setSelectedFiles((prev) => {
      const combined = [...prev, ...newFiles];
      const nameSet = new Set<string>();
      return combined.map(item => {
        const dup = nameSet.has(item.file.name);
        nameSet.add(item.file.name);
        return { ...item, isDuplicate: dup };
      });
    });
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleImageSelect = (fileList: FileList | null) => {
    if (!fileList?.length) return;
    const newFiles = Array.from(fileList)
      .filter(f => f.type.startsWith('image/'))
      .map(f => ({ file: f, imageId: '', status: 'pending' as const }));
    setSelectedImages(prev => [...prev, ...newFiles]);
    if (imageInputRef.current) imageInputRef.current.value = '';
  };

  const handleRowImageSelect = async (fileList: FileList | null) => {
    if (!fileList?.length || pendingRowImageIndex === null) return;
    const file = fileList[0];
    if (!file.type.startsWith('image/')) return;

    const index = pendingRowImageIndex;
    setPendingRowImageIndex(null);

    setRows(prev => prev.map((r, i) => i === index ? { ...r, imgStatus: 'uploading' } : r));
    try {
      const res = await onUploadImage(file);
      const imageId = res.image_id || res.id || res.name; // Backend returns image_id
      setRows(prev => prev.map((r, i) => i === index ? { ...r, img: imageId, imgStatus: 'done', imgError: undefined } : r));
    } catch (err: any) {
      setRows(prev => prev.map((r, i) => i === index ? { ...r, imgStatus: 'error', imgError: err.message || String(err) } : r));
    }
    if (rowImageInputRef.current) rowImageInputRef.current.value = '';
  };

  const handleUploadFiles = async () => {
    const pendingFiles = selectedFiles.map((f, i) => ({ item: f, index: i }))
      .filter(f => f.item.status === 'pending' || f.item.status === 'error');
    if (!pendingFiles.length) return;

    setUploadingLocal(true);
    const resolved = topic.resolveIds();
    let firstUploadedFileName: string | null = null;
    let successCount = 0;

    for (const { item, index } of pendingFiles) {
      setSelectedFiles(prev => prev.map((f, i) => i === index ? { ...f, status: 'uploading' } : f));
      try {
        const res = await onUploadFile(item.file, resolved?.fullTopicId || null, resolved?.labels || null);
        if (!firstUploadedFileName) firstUploadedFileName = res.name;
        successCount++;
        setSelectedFiles(prev => prev.map((f, i) => i === index ? { ...f, status: 'done', error: undefined } : f));
      } catch (err: any) {
        setSelectedFiles(prev => prev.map((f, i) => i === index ? { ...f, status: 'error', error: err.message || String(err) } : f));
      }
    }

    setUploadingLocal(false);
    if (successCount > 0) await onUploadComplete(firstUploadedFileName, successCount);
  };

  const handleSubmitQA = async () => {
    const resolved = topic.resolveIds();
    if (!validRows.length || !resolved) return;

    setUploadingLocal(true);
    try {
      const prefix = (resolved.fullTopicId.split('/').pop() || resolved.fullTopicId).toUpperCase().replace(/-/g, '_');
      const blob = buildCsvBlob(validRows, prefix);
      const file = new File([blob], `${prefix.toLowerCase()}_qa_${Date.now()}.csv`, { type: 'text/csv' });
      await onSubmitQA(file, resolved.fullTopicId, resolved.labels);
    } finally {
      setUploadingLocal(false);
    }
  };

  const handleUploadImages = async () => {
    const pending = selectedImages.map((f, i) => ({ item: f, index: i }))
      .filter(f => f.item.status === 'pending' || f.item.status === 'error');
    if (!pending.length) return;

    setUploadingLocal(true);
    let successCount = 0;
    for (const { item, index } of pending) {
      setSelectedImages(prev => prev.map((f, i) => i === index ? { ...f, status: 'uploading' } : f));
      try {
        await onUploadImage(item.file, item.imageId.trim() || undefined);
        successCount++;
        setSelectedImages(prev => prev.map((f, i) => i === index ? { ...f, status: 'done', error: undefined } : f));
      } catch (err: any) {
        setSelectedImages(prev => prev.map((f, i) => i === index ? { ...f, status: 'error', error: err.message || String(err) } : f));
      }
    }
    setUploadingLocal(false);
    if (successCount > 0) await onUploadImageComplete(successCount);
  };

  function getFileIcon(filename: string) {
    const ext = filename.split('.').pop()?.toLowerCase();
    if (ext === 'csv') return <Table size={16} style={{ color: '#3b82f6' }} />;
    if (ext === 'pdf') return <FileText size={16} style={{ color: '#ef4444' }} />;
    if (ext === 'docx' || ext === 'doc') return <FileType size={16} style={{ color: '#1d4ed8' }} />;
    if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext || '')) return <ImageIcon size={16} style={{ color: '#22c55e' }} />;
    return <FileIcon size={16} style={{ color: '#6b7280' }} />;
  }

  function getStatusIcon(status: FileStatus, error?: string) {
    if (status === 'uploading') return <Loader2 size={16} style={{ color: '#3b82f6', animation: 'spin 1s linear infinite' }} />;
    if (status === 'done') return <CheckCircle2 size={16} style={{ color: '#22c55e' }} />;
    if (status === 'error') return <span title={error}><XCircle size={16} style={{ color: '#ef4444' }} /></span>;
    return null;
  }

  if (!open) return null;

  return (
    <div className="hciot-qa-overlay" onClick={onClose}>
      <div className="hciot-qa-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="hciot-qa-header">
          <h3>{language === 'zh' ? '新增內容' : 'Add Content'}</h3>
          <button type="button" className="hciot-qa-close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="hciot-upload-tabs" role="tablist">
          {[
            { id: 'file', labelZh: '上傳知識檔', labelEn: 'Upload Files', icon: Upload },
            { id: 'qa', labelZh: '手動輸入 Q&A', labelEn: 'Manual Q&A', icon: Plus },
            { id: 'image', labelZh: '上傳圖片', labelEn: 'Upload Images', icon: ImageIcon },
          ].map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              className={`hciot-upload-tab${tab === t.id ? ' is-active' : ''}`}
              onClick={() => setTab(t.id as Tab)}
              aria-selected={tab === t.id}
            >
              <t.icon size={14} />
              {language === 'zh' ? t.labelZh : t.labelEn}
            </button>
          ))}
        </div>

        {tab !== 'image' && (
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

            {topic.categoryId === NEW_VALUE && (
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
            )}

            {topic.topicId === NEW_VALUE && (
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
            )}
          </div>
        )}

        {tab === 'file' && (
          <UploadTabBody
            language={language}
            dragOver={dragOver}
            setDragOver={setDragOver}
            inputRef={fileInputRef}
            items={selectedFiles}
            isUploading={uploadingLocal || uploading}
            disabled={!canSubmitFile}
            dropLabelZh="點擊或拖放檔案"
            dropLabelEn="Click or drop files here"
            dropSubZh="支援 CSV、PDF、TXT、Word 等"
            dropSubEn="CSV, PDF, TXT, Word, etc."
            countZh="個檔案"
            countEn="file(s)"
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              if (e.dataTransfer.files.length) handleFileSelect(e.dataTransfer.files);
            }}
            onSelect={handleFileSelect}
            onUpload={() => void handleUploadFiles()}
            onClose={onClose}
            renderItem={(item, i) => (
              <div key={`${item.file.name}-${i}`} className="hciot-upload-file-item" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                {getFileIcon(item.file.name)}
                <span className="hciot-upload-file-name" style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.file.name}</span>
                {item.isDuplicate && (
                  <span className="hciot-file-warning" title={language === 'zh' ? '重複檔名' : 'Duplicate filename'} style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', color: '#f59e0b' }}>
                    <AlertCircle size={12} />
                    {language === 'zh' ? '(重複)' : '(Dup)'}
                  </span>
                )}
                <span className="hciot-upload-file-size" style={{ minWidth: '60px', textAlign: 'right' }}>
                  {item.file.size > 1024 ? `${(item.file.size / 1024).toFixed(1)} KB` : `${item.file.size} B`}
                </span>
                <div className="hciot-file-actions" style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: '40px', justifyContent: 'flex-end' }}>
                  {getStatusIcon(item.status, item.error)}
                  {item.status !== 'uploading' && item.status !== 'done' && (
                    <button type="button" className="hciot-qa-row-delete" onClick={() => setSelectedFiles(prev => prev.filter((_, idx) => idx !== i))} title={language === 'zh' ? '移除' : 'Remove'}>
                      <X size={14} />
                    </button>
                  )}
                </div>
              </div>
            )}
          />
        )}

        {tab === 'image' && (
          <UploadTabBody
            language={language}
            dragOver={dragOver}
            setDragOver={setDragOver}
            inputRef={imageInputRef}
            items={selectedImages}
            isUploading={uploadingLocal}
            disabled={!canSubmitImage}
            accept="image/*"
            dropLabelZh="點擊或拖放圖片檔案"
            dropLabelEn="Click or drop image files here"
            dropSubZh="支援 JPG、PNG、GIF、WEBP (最大 10MB)"
            dropSubEn="JPG, PNG, GIF, WEBP (Max 10MB)"
            countZh="張圖片"
            countEn="image(s)"
            listStyle={{ maxHeight: '300px', overflowY: 'auto' }}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              if (e.dataTransfer.files.length) handleImageSelect(e.dataTransfer.files);
            }}
            onSelect={handleImageSelect}
            onUpload={() => void handleUploadImages()}
            onClose={onClose}
            renderItem={(item, i) => (
              <div key={`${item.file.name}-${i}`} className="hciot-upload-file-item" style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px' }}>
                <ImageIcon size={16} className="text-green-500" />
                <div style={{ display: 'flex', flexDirection: 'column', flex: 1, gap: '4px', minWidth: 0 }}>
                  <span className="hciot-upload-file-name" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.file.name}</span>
                  <input
                    type="text"
                    placeholder={language === 'zh' ? '自訂 IMG ID (選填)' : 'Custom IMG ID (optional)'}
                    value={item.imageId}
                    onChange={(e) => setSelectedImages(prev => prev.map((img, idx) => idx === i ? { ...img, imageId: e.target.value } : img))}
                    disabled={item.status === 'uploading' || item.status === 'done'}
                    className="hciot-file-input"
                    style={{ fontSize: '12px', padding: '2px 6px', height: '24px' }}
                  />
                </div>
                <span className="hciot-upload-file-size" style={{ minWidth: '60px', textAlign: 'right' }}>
                  {item.file.size > 1024 ? `${(item.file.size / 1024).toFixed(1)} KB` : `${item.file.size} B`}
                </span>
                <div className="hciot-file-actions" style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: '40px', justifyContent: 'flex-end' }}>
                  {getStatusIcon(item.status, item.error)}
                  {item.status !== 'uploading' && item.status !== 'done' && (
                    <button type="button" className="hciot-qa-row-delete" onClick={() => setSelectedImages(prev => prev.filter((_, idx) => idx !== i))} title={language === 'zh' ? '移除' : 'Remove'}>
                      <X size={14} />
                    </button>
                  )}
                </div>
              </div>
            )}
          />
        )}

        {tab === 'qa' && (
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
                  <div className="hciot-qa-row-image">
                    <button
                      type="button"
                      className={`hciot-qa-image-btn ${row.imgStatus}`}
                      onClick={() => {
                        setPendingRowImageIndex(index);
                        rowImageInputRef.current?.click();
                      }}
                      title={row.img ? (row.img) : (language === 'zh' ? '上傳圖片' : 'Upload Image')}
                    >
                      {row.imgStatus === 'uploading' ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : row.img ? (
                        <CheckCircle2 size={14} className="text-green-500" />
                      ) : row.imgStatus === 'error' ? (
                        <span title={row.imgError} className="flex"><XCircle size={14} className="text-red-500" /></span>
                      ) : (
                        <ImageIcon size={14} />
                      )}
                    </button>
                    {row.img && (
                      <button
                        type="button"
                        className="hciot-qa-image-clear"
                        onClick={() => setRows(prev => prev.map((r, i) => i === index ? { ...r, img: '', imgStatus: 'pending' } : r))}
                      >
                        <X size={10} />
                      </button>
                    )}
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
            <input
              ref={rowImageInputRef}
              type="file"
              hidden
              accept="image/*"
              onChange={(e) => handleRowImageSelect(e.target.files)}
            />

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
                  {uploadingLocal || uploading
                    ? (language === 'zh' ? '上傳中...' : 'Uploading...')
                    : (language === 'zh' ? '上傳' : 'Upload')}
                </button>
              </div>
            </div>
          </div>
        )}

        <style>{`
          @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
          }
          .hciot-qa-row-image {
            display: flex;
            align-items: center;
            gap: 4px;
            position: relative;
          }
          .hciot-qa-image-btn {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 28px;
            height: 28px;
            border: 1px solid #e5e7eb;
            border-radius: 4px;
            background: #f9fafb;
            color: #6b7280;
            cursor: pointer;
            transition: all 0.2s;
          }
          .hciot-qa-image-btn:hover {
            background: #f3f4f6;
            border-color: #d1d5db;
          }
          .hciot-qa-image-btn.done {
            border-color: #22c55e;
            background: #f0fdf4;
            color: #22c55e;
          }
          .hciot-qa-image-btn.error {
            border-color: #ef4444;
            background: #fef2f2;
            color: #ef4444;
          }
          .hciot-qa-image-clear {
            position: absolute;
            top: -6px;
            right: -6px;
            width: 16px;
            height: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #9ca3af;
            color: white;
            border-radius: 50%;
            border: none;
            cursor: pointer;
          }
          .hciot-qa-image-clear:hover {
            background: #6b7280;
          }
        `}</style>
      </div>
    </div>
  );
}
