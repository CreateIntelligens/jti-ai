import { useState, useRef } from 'react';
import type { Store, FileItem } from '../types';

interface SidebarProps {
  isOpen: boolean;
  stores: Store[];
  currentStore: string | null;
  files: FileItem[];
  filesLoading: boolean;
  onStoreChange: (storeName: string) => void;
  onUploadFile: (file: File) => void;
  onDeleteFile: (fileName: string) => void;
  onRefresh: () => void;
  onOpenPromptManagement: () => void;
}

export default function Sidebar({
  isOpen,
  stores,
  currentStore,
  files,
  filesLoading,
  onStoreChange,
  onUploadFile,
  onDeleteFile,
  onRefresh,
  onOpenPromptManagement,
}: SidebarProps) {
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = () => {
    setDragOver(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (uploading) return;

    const file = e.dataTransfer.files[0];
    if (file) {
      setUploading(true);
      await onUploadFile(file);
      setUploading(false);
    }
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setUploading(true);
      await onUploadFile(file);
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  return (
    <aside className={isOpen ? '' : 'closed'} aria-label="側邊欄">
      <div className="sidebar-section fixed-section">
        <h2>知識庫</h2>
        <select
          value={currentStore || ''}
          onChange={e => onStoreChange(e.target.value)}
          className="w-full"
          aria-label="選擇知識庫"
        >
          {stores.length === 0 && (
            <option value="">尚無知識庫</option>
          )}
          {stores.map(store => (
            <option key={store.name} value={store.name}>
              {store.display_name || store.name}
            </option>
          ))}
        </select>
        <button
          onClick={onRefresh}
          className="secondary w-full mt-sm"
          aria-label="重新整理知識庫列表"
        >
          ⟳ 重新整理
        </button>
      </div>

      <div className="sidebar-section scrollable-section">
        <h2>文件</h2>
        <div
          className={`drop-zone ${dragOver ? 'dragover' : ''} ${uploading ? 'uploading' : ''}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          role="button"
          tabIndex={0}
          aria-label="上傳文件區域"
        >
          <p>
            {uploading ? '上傳中...' : (
              <>
                拖曳文件至此或{' '}
                <span className="browse-link">瀏覽</span>
              </>
            )}
          </p>
          <input
            ref={fileInputRef}
            type="file"
            onChange={handleFileSelect}
            style={{ display: 'none' }}
            aria-label="選擇文件"
          />
        </div>

        <div className="file-list-container">
          {filesLoading ? (
            <ul className="file-list" aria-label="載入中">
              {[1, 2, 3].map(i => (
                <li key={i} className="file-skeleton">
                  <div className="skeleton-bar" style={{ width: `${50 + i * 12}%` }} />
                </li>
              ))}
            </ul>
          ) : files.length > 0 ? (
            <ul className="file-list" aria-label="文件列表">
              {files.map((file, i) => (
                <li key={file.name} className="file-item-enter" style={{ animationDelay: `${i * 40}ms` }}>
                  <span>{file.display_name || file.name}</span>
                  <button
                    onClick={() => onDeleteFile(file.name)}
                    className="danger small"
                    aria-label={`刪除文件 ${file.display_name || file.name}`}
                  >
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p style={{ color: '#8090b0', fontSize: '0.9rem', textAlign: 'center' }}>
              尚無文件
            </p>
          )}
        </div>
      </div>

      <div className="sidebar-section sidebar-footer">
        <button
          onClick={onOpenPromptManagement}
          className="secondary w-full"
          aria-label="開啟設置"
        >
          ⚙ 設置
        </button>
      </div>
    </aside>
  );
}
