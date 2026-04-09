import type { CSSProperties, ReactNode, RefObject } from 'react';
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
  listStyle?: CSSProperties;
}

export default function UploadTabBody<T>({
  language,
  dragOver,
  setDragOver,
  onDrop,
  onSelect,
  inputRef,
  accept,
  items,
  renderItem,
  isUploading,
  disabled,
  onUpload,
  onClose,
  dropLabelZh,
  dropLabelEn,
  dropSubZh,
  dropSubEn,
  countZh,
  countEn,
  listStyle,
}: UploadTabBodyProps<T>) {
  return (
    <div className="hciot-upload-file-body">
      <div
        className={`hciot-upload-dropzone${dragOver ? ' is-drag-over' : ''}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setDragOver(true);
        }}
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
        onChange={(event) => onSelect(event.target.files)}
      />

      {items.length > 0 && (
        <div className="hciot-upload-file-list" style={listStyle}>
          {items.map((item, index) => renderItem(item, index))}
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
