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
  hint?: ReactNode;
}

export default function UploadTabBody<T>({
  language: _language,
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
  dropLabelEn: _dropLabelEn,
  dropSubZh,
  dropSubEn: _dropSubEn,
  countZh,
  countEn: _countEn,
  listStyle,
  hint,
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
        <p>{dropLabelZh}</p>
        <span>{dropSubZh}</span>
      </div>
      <input
        ref={inputRef}
        type="file"
        hidden
        multiple
        accept={accept}
        onChange={(event) => onSelect(event.target.files)}
      />

      {hint}

      {items.length > 0 && (
        <div className="hciot-upload-file-list custom-scrollbar" style={listStyle}>
          {items.map((item, index) => renderItem(item, index))}
        </div>
      )}

      <div className="hciot-qa-footer">
        <span className="hciot-qa-count">
          {items.length} {countZh}
        </span>
        <div className="hciot-qa-footer-actions">
          <button type="button" className="hciot-file-action-button" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            className="hciot-file-action-button primary"
            disabled={disabled}
            onClick={onUpload}
          >
            <Upload size={14} />
            {isUploading ? '上傳中...' : '上傳'}
          </button>
        </div>
      </div>
    </div>
  );
}
