import { useEffect, useRef, useState } from 'react';
import { AlertCircle, File as FileIcon, FileText, FileType, Image as ImageIcon, Table, X } from 'lucide-react';

import type { HciotLanguage } from '../../../../config/hciotTopics';
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

function getFileIcon(filename: string) {
  const ext = filename.split('.').pop()?.toLowerCase();
  if (ext === 'csv') return <Table size={16} className="hciot-icon-blue" />;
  if (ext === 'pdf') return <FileText size={16} className="hciot-icon-red" />;
  if (ext === 'docx' || ext === 'doc') return <FileType size={16} className="hciot-icon-dark-blue" />;
  if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext || '')) return <ImageIcon size={16} className="hciot-icon-green" />;
  return <FileIcon size={16} className="hciot-icon-muted" />;
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

  const canSubmitFile = selectedFiles.some((item) => item.status === 'pending' || item.status === 'error')
    && !uploadingLocal
    && !uploading;

  const handleFileSelect = (fileList: FileList | null) => {
    if (!fileList?.length) {
      return;
    }

    const newFiles = Array.from(fileList).map((file) => ({
      file,
      status: 'pending' as const,
      isDuplicate: false,
    }));

    setSelectedFiles((previous) => {
      const combined = [...previous, ...newFiles];
      const nameSet = new Set<string>();
      return combined.map((item) => {
        const isDuplicate = nameSet.has(item.file.name);
        nameSet.add(item.file.name);
        return { ...item, isDuplicate };
      });
    });

    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
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
      renderItem={(item, index) => (
        <div key={`${item.file.name}-${index}`} className="hciot-upload-file-item hciot-upload-item-content">
          {getFileIcon(item.file.name)}
          <span className="hciot-upload-file-name hciot-upload-name-text">
            {item.file.name}
          </span>
          {item.isDuplicate && (
            <span
              className="hciot-file-warning hciot-file-warning-badge hciot-icon-warning"
              title={language === 'zh' ? '重複檔名' : 'Duplicate filename'}
            >
              <AlertCircle size={12} />
              {language === 'zh' ? '(重複)' : '(Dup)'}
            </span>
          )}
          <span className="hciot-upload-file-size hciot-upload-size-text">
            {item.file.size > 1024 ? `${(item.file.size / 1024).toFixed(1)} KB` : `${item.file.size} B`}
          </span>
          <div className="hciot-file-actions">
            <UploadStatusIcon status={item.status} error={item.error} />
            {item.status !== 'uploading' && item.status !== 'done' && (
              <button
                type="button"
                className="hciot-qa-row-delete"
                onClick={() => setSelectedFiles((previous) => previous.filter((_, itemIndex) => itemIndex !== index))}
                title={language === 'zh' ? '移除' : 'Remove'}
              >
                <X size={14} />
              </button>
            )}
          </div>
        </div>
      )}
    />
  );
}
