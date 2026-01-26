import { useState, useRef } from 'react';
import type { Store, FileItem } from '../types';

interface SidebarProps {
  isOpen: boolean;
  stores: Store[];
  currentStore: string | null;
  files: FileItem[];
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
    <aside className={isOpen ? '' : 'closed'}>
      <div className="sidebar-section fixed-section">
        <h2>知識庫</h2>
        <select
          value={currentStore || ''}
          onChange={e => onStoreChange(e.target.value)}
          className="w-full"
        >
          <option value="">選擇知識庫...</option>
          {stores.map(store => (
            <option key={store.name} value={store.name}>
              {store.display_name || store.name}
            </option>
          ))}
        </select>
        <button
          onClick={onRefresh}
          className="secondary w-full mt-sm"
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
          />
        </div>

        <div className="file-list-container">
          {files.length > 0 ? (
            <ul className="file-list">
              {files.map(file => (
                <li key={file.name}>
                  <span>{file.display_name || file.name}</span>
                  <button
                    onClick={() => onDeleteFile(file.name)}
                    className="danger small"
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
        >
          ⚙ 自訂 Prompt
        </button>
      </div>
    </aside>
  );
}
