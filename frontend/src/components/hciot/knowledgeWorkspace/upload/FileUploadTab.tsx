import { useEffect, useRef, useState } from 'react';
import { AlertCircle, ChevronDown, ChevronRight, Download, File as FileIcon, FileText, FileType, Image as ImageIcon, Table, X } from 'lucide-react';

import type { HciotLanguage } from '../../../../config/hciotTopics';
import { downloadBlob } from '../../../../utils/download';
import type { TopicLabels } from '../topicUtils';
import UploadStatusIcon from './UploadStatusIcon';
import UploadTabBody from './UploadTabBody';
import type { FileItem, ResolvedUploadTopic } from './types';

interface FileUploadTabProps {
  open: boolean;
  language: HciotLanguage;
  uploading: boolean;
  resolvedTopic: ResolvedUploadTopic | null;
  onClose: () => void;
  onUploadFile: (file: File, topicId: string | null, labels: TopicLabels | null) => Promise<{ name: string }>;
  onUploadComplete: (firstUploadedFileName: string | null, count: number) => Promise<void>;
}

const FILE_ICON_MAP: Record<string, { icon: typeof FileIcon, color: string }> = {
  csv: { icon: Table, color: 'hciot-icon-blue' },
  pdf: { icon: FileText, color: 'hciot-icon-red' },
  docx: { icon: FileType, color: 'hciot-icon-dark-blue' },
  doc: { icon: FileType, color: 'hciot-icon-dark-blue' },
  jpg: { icon: ImageIcon, color: 'hciot-icon-green' },
  jpeg: { icon: ImageIcon, color: 'hciot-icon-green' },
  png: { icon: ImageIcon, color: 'hciot-icon-green' },
  gif: { icon: ImageIcon, color: 'hciot-icon-green' },
  webp: { icon: ImageIcon, color: 'hciot-icon-green' },
};

function getFileIcon(filename: string) {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  const { icon: Icon, color } = FILE_ICON_MAP[ext] || { icon: FileIcon, color: 'hciot-icon-muted' };
  return <Icon size={16} className={color} />;
}

const CSV_SAMPLE_ZH = `q,a,img
什麼是高血壓？,血壓持續偏高的狀態，收縮壓 ≥140 mmHg 或舒張壓 ≥90 mmHg。,
如何量血壓？,請先靜坐5分鐘，再將血壓計袖帶套在上臂並按下量測鍵。,IMG_BP_001
`;
const CSV_SAMPLE_EN = `q,a,img
What is hypertension?,A condition where blood pressure is consistently elevated (systolic ≥140 mmHg or diastolic ≥90 mmHg).,
How to measure blood pressure?,Sit quietly for 5 minutes then place the cuff on your upper arm and press the start button.,IMG_BP_001
`;

function downloadCsvSample(language: HciotLanguage) {
  const content = language === 'zh' ? CSV_SAMPLE_ZH : CSV_SAMPLE_EN;
  const filename = language === 'zh' ? 'qa_sample_zh.csv' : 'qa_sample_en.csv';
  downloadBlob(new Blob([content], { type: 'text/csv;charset=utf-8' }), filename);
}

const I18N = {
  zh: {
    csvHint: 'CSV 格式範例',
    downloadSample: '下載範例',
    downloadTitle: '下載範例 CSV',
    q: '問題（必填）',
    a: '回答',
    img: '圖片 檔名（選填，不需要副檔名）',
    qText1: '什麼是高血壓？',
    aText1: '血壓持續偏高的狀態...',
    qText2: '如何量血壓？',
    aText2: '請先靜坐5分鐘...',
    duplicate: '(重複)',
    duplicateTitle: '重複檔名',
    remove: '移除',
  },
  en: {
    csvHint: 'CSV Format Example',
    downloadSample: 'Download',
    downloadTitle: 'Download sample CSV',
    q: 'Question (required)',
    a: 'Answer',
    img: 'Image ID (optional, upload image first)',
    qText1: 'What is hypertension?',
    aText1: 'A condition where blood pressure is consistently elevated...',
    qText2: 'How to measure blood pressure?',
    aText2: 'Please sit quietly for 5 minutes...',
    duplicate: '(Dup)',
    duplicateTitle: 'Duplicate filename',
    remove: 'Remove',
  },
};

function CsvFormatHint({ language }: { language: HciotLanguage }) {
  const [expanded, setExpanded] = useState(false);
  const t = I18N[language];

  return (
    <div className="hciot-csv-hint">
      <div className="hciot-csv-hint-header">
        <button
          type="button"
          className="hciot-csv-hint-toggle"
          onClick={() => setExpanded((prev) => !prev)}
        >
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          {t.csvHint}
        </button>
        <button
          type="button"
          className="hciot-csv-hint-download"
          onClick={() => downloadCsvSample(language)}
          title={t.downloadTitle}
        >
          <Download size={13} />
          {t.downloadSample}
        </button>
      </div>
      {expanded && (
        <div className="hciot-csv-hint-content">
          <table className="hciot-csv-hint-table">
            <thead>
              <tr>
                <th>q</th>
                <th>a</th>
                <th>img</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>{t.qText1}</td>
                <td>{t.aText1}</td>
                <td></td>
              </tr>
              <tr>
                <td>{t.qText2}</td>
                <td>{t.aText2}</td>
                <td>IMG_BP_001</td>
              </tr>
            </tbody>
          </table>
          <ul className="hciot-csv-hint-notes">
            <li><strong>q</strong> — {t.q}</li>
            <li><strong>a</strong> — {t.a}</li>
            <li><strong>img</strong> — {t.img}</li>
          </ul>
        </div>
      )}
    </div>
  );
}

export default function FileUploadTab({
  open,
  language,
  uploading,
  resolvedTopic,
  onClose,
  onUploadFile,
  onUploadComplete,
}: FileUploadTabProps) {
  const [dragOver, setDragOver] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<FileItem[]>([]);
  const [uploadingLocal, setUploadingLocal] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setDragOver(false);
      setSelectedFiles([]);
      setUploadingLocal(false);
    }
  }, [open]);

  const isBusy = uploadingLocal || uploading;
  const hasPending = selectedFiles.some((item) => item.status === 'pending' || item.status === 'error');
  const canSubmitFile = hasPending && !isBusy;

  const handleFileSelect = (fileList: FileList | null) => {
    if (!fileList?.length) return;

    const newFiles = Array.from(fileList).map((file) => ({
      file,
      status: 'pending' as const,
      isDuplicate: false,
    }));

    setSelectedFiles((prev) => {
      const combined = [...prev, ...newFiles];
      const nameSet = new Set<string>();
      return combined.map((item) => {
        const isDuplicate = nameSet.has(item.file.name);
        nameSet.add(item.file.name);
        return { ...item, isDuplicate };
      });
    });

    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const updateFileStatus = (index: number, updates: Partial<FileItem>) => {
    setSelectedFiles((previous) => previous.map((fileItem, itemIndex) => (
      itemIndex === index ? { ...fileItem, ...updates } : fileItem
    )));
  };

  const handleUploadFiles = async () => {
    const pendingFiles = selectedFiles
      .map((item, index) => ({ item, index }))
      .filter(({ item }) => item.status === 'pending' || item.status === 'error');
    if (!pendingFiles.length) {
      return;
    }

    setUploadingLocal(true);
    let firstUploadedFileName: string | null = null;
    let successCount = 0;

    for (const { item, index } of pendingFiles) {
      updateFileStatus(index, { status: 'uploading' });

      try {
        const response = await onUploadFile(
          item.file,
          resolvedTopic?.fullTopicId || null,
          resolvedTopic?.labels || null,
        );
        if (!firstUploadedFileName) {
          firstUploadedFileName = response.name;
        }
        successCount += 1;
        updateFileStatus(index, { status: 'done', error: undefined });
      } catch (error: any) {
        updateFileStatus(index, { status: 'error', error: error.message || String(error) });
      }
    }

    setUploadingLocal(false);
    if (successCount > 0) {
      await onUploadComplete(firstUploadedFileName, successCount);
    }
  };

  return (
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
      dropSubZh="只支援 CSV"
      dropSubEn="CSV only"
      countZh="個檔案"
      countEn="file(s)"
      hint={<CsvFormatHint language={language} />}
      onDrop={(event) => {
        event.preventDefault();
        setDragOver(false);
        if (event.dataTransfer.files.length) {
          handleFileSelect(event.dataTransfer.files);
        }
      }}
      onSelect={handleFileSelect}
      onUpload={() => { void handleUploadFiles(); }}
      onClose={onClose}
      renderItem={(item, index) => {
        const t = I18N[language];
        const fileSize = item.file.size > 1024
          ? `${(item.file.size / 1024).toFixed(1)} KB`
          : `${item.file.size} B`;

        return (
          <div key={`${item.file.name}-${index}`} className="hciot-upload-file-item">
            {getFileIcon(item.file.name)}
            <span className="hciot-upload-file-name">{item.file.name}</span>
            {item.isDuplicate && (
              <span
                className="hciot-file-warning hciot-file-warning-badge hciot-icon-warning"
                title={t.duplicateTitle}
              >
                <AlertCircle size={12} />
                {t.duplicate}
              </span>
            )}
            <span className="hciot-upload-file-size">{fileSize}</span>
            <div className="hciot-file-actions">
              <UploadStatusIcon status={item.status} error={item.error} />
              {!['uploading', 'done'].includes(item.status) && (
                <button
                  type="button"
                  className="hciot-qa-row-delete"
                  onClick={() => setSelectedFiles((prev) => prev.filter((_, i) => i !== index))}
                  title={t.remove}
                >
                  <X size={14} />
                </button>
              )}
            </div>
          </div>
        );
      }}
    />
  );
}
