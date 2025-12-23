import { useState, useRef } from 'react';

export default function FileDropZone({ onUpload, disabled }) {
  const [dragover, setDragover] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState('');
  const fileInputRef = useRef(null);
  const folderInputRef = useRef(null);

  const getAllFiles = async (dataTransferItems) => {
    const files = [];
    
    const traverseDirectory = async (entry) => {
      if (entry.isFile) {
        return new Promise((resolve) => {
          entry.file((file) => {
            files.push(file);
            resolve();
          });
        });
      } else if (entry.isDirectory) {
        const reader = entry.createReader();
        return new Promise((resolve) => {
          reader.readEntries(async (entries) => {
            for (const entry of entries) {
              await traverseDirectory(entry);
            }
            resolve();
          });
        });
      }
    };

    for (const item of dataTransferItems) {
      const entry = item.webkitGetAsEntry();
      if (entry) {
        await traverseDirectory(entry);
      }
    }
    
    return files;
  };

  const handleDrop = async (e) => {
    e.preventDefault();
    setDragover(false);
    
    const items = Array.from(e.dataTransfer.items);
    const files = await getAllFiles(items);
    
    if (files.length > 0) {
      await handleMultipleUpload(files);
    }
  };

  const handleFileSelect = async (e) => {
    const files = Array.from(e.target.files);
    if (files.length > 0) {
      await handleMultipleUpload(files);
    }
    e.target.value = '';
  };

  const handleMultipleUpload = async (files) => {
    setUploading(true);
    let successCount = 0;
    let failCount = 0;

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      setUploadProgress(`上傳中 ${i + 1}/${files.length}: ${file.name}`);
      
      try {
        await onUpload(file);
        successCount++;
      } catch (error) {
        console.error(`上傳失敗: ${file.name}`, error);
        failCount++;
      }
    }

    setUploading(false);
    setUploadProgress('');
    
    if (failCount > 0) {
      alert(`上傳完成！成功: ${successCount}, 失敗: ${failCount}`);
    }
  };

  return (
    <div style={{ marginBottom: '1rem' }}>
      <div
        className={`drop-zone ${dragover ? 'dragover' : ''} ${uploading ? 'uploading' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragover(true); }}
        onDragLeave={() => setDragover(false)}
        onDrop={handleDrop}
        style={{ cursor: 'default', marginBottom: '0.5rem' }}
      >
        <input
          type="file"
          ref={fileInputRef}
          style={{ display: 'none' }}
          onChange={handleFileSelect}
          disabled={disabled || uploading}
          multiple
        />
        <input
          type="file"
          ref={folderInputRef}
          style={{ display: 'none' }}
          onChange={handleFileSelect}
          disabled={disabled || uploading}
          webkitdirectory=""
          directory=""
          multiple
        />
        <p style={{ marginBottom: '0.75rem' }}>
          {uploading ? uploadProgress || '上傳中...' : '拖曳檔案或資料夾至此'}
        </p>
        {!uploading && (
          <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center' }}>
            <button
              type="button"
              className="secondary"
              onClick={(e) => {
                e.stopPropagation();
                !disabled && fileInputRef.current?.click();
              }}
              disabled={disabled}
              style={{ fontSize: '0.85rem', padding: '0.4rem 1rem' }}
            >
              選擇檔案
            </button>
            <button
              type="button"
              className="secondary"
              onClick={(e) => {
                e.stopPropagation();
                !disabled && folderInputRef.current?.click();
              }}
              disabled={disabled}
              style={{ fontSize: '0.85rem', padding: '0.4rem 1rem' }}
            >
              選擇資料夾
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
