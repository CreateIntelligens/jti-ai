import type { ReactNode, RefObject } from 'react';
import { Upload } from 'lucide-react';

import type { HciotLanguage } from '../../../../config/hciotTopics';

interface UploadTabBodyProps<T> {
  language: HciotLanguage;
  dragOver: boolean;
  setDragOver: (over: boolean) => void;
  onDrop: (event: React.DragEvent) => void;
  onSelect: (fileList: FileList | null) => void;
  inputRef: RefObject<HTMLInputElement | null>;
  accept?: string;
  multiple?: boolean;
  items: T[];
  renderItem: (item: T, index: number) => ReactNode;
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
  fileListClassName?: string;
  hint?: ReactNode;
  afterContent?: ReactNode;
  uploadLabel?: string;
  extraFooterActions?: ReactNode;
}

export default function UploadTabBody<T>({
  language: _language,
  dragOver,
  setDragOver,
  onDrop,
  onSelect,
  inputRef,
  accept,
  multiple = true,
  items,
  renderItem,
  isUploading,
  disabled,
  onUpload,
  onClose,
  dropLabelZh,
  dropLabelEn: _dropLabelEn,
  dropSubZh,
  dropSubEn: _dropSubEn,
  countZh,
  countEn: _countEn,
  fileListClassName,
  hint,
  afterContent,
  uploadLabel,
  extraFooterActions,
}: UploadTabBodyProps<T>) {
  const fileListClasses = [
    'qa-workspace-upload-file-list',
    'custom-scrollbar',
    fileListClassName,
  ].filter(Boolean).join(' ');

  return (
    <div className="qa-workspace-upload-file-body">
      <div
        className={`qa-workspace-upload-dropzone${dragOver ? ' is-drag-over' : ''}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
      >
        <Upload size={24} />
        <p>{dropLabelZh}</p>
        <span>{dropSubZh}</span>
      </div>
      <input
        ref={inputRef}
        type="file"
        hidden
        multiple={multiple}
        accept={accept}
        onChange={(event) => onSelect(event.target.files)}
      />

      {hint}

      {items.length > 0 && (
        <div className={fileListClasses}>
          {items.map((item, index) => renderItem(item, index))}
        </div>
      )}

      {afterContent}

      <div className="qa-workspace-qa-footer">
        <span className="qa-workspace-qa-count">
          {items.length} {countZh}
        </span>
        <div className="qa-workspace-qa-footer-actions">
          <button type="button" className="qa-workspace-file-action-button" onClick={onClose}>
            取消
          </button>
          {extraFooterActions}
          <button
            type="button"
            className="qa-workspace-file-action-button primary"
            disabled={disabled}
            onClick={onUpload}
          >
            <Upload size={14} />
            {isUploading ? '上傳中...' : (uploadLabel || '上傳')}
          </button>
        </div>
      </div>
    </div>
  );
}
