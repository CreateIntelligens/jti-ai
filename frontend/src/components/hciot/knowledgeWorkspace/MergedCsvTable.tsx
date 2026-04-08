import { Plus, Trash2, Upload, X } from 'lucide-react';
import type { HciotMergedCsvRow } from '../../../services/api/hciot';
import type { HciotLanguage } from '../../../config/hciotTopics';
import { getHciotImageUrl, normalizeImageId } from '../../../utils/hciotImage';
import { useState } from 'react';

interface MergedCsvTableProps {
  topicId: string;
  language: HciotLanguage;
  rows: HciotMergedCsvRow[];
  sourceFiles: string[];
  loading: boolean;
  error: string | null;
  isEditing: boolean;
  onUpdateRow: (index: number, updated: Partial<HciotMergedCsvRow>) => void;
  onDeleteRow: (index: number) => void;
  onAddRow: () => void;
  onUploadImage?: (file: File) => Promise<{ image_id: string }>;
}

export default function MergedCsvTable({
  language,
  rows,
  sourceFiles,
  loading,
  error,
  isEditing,
  onUpdateRow,
  onDeleteRow,
  onAddRow,
  onUploadImage,
}: MergedCsvTableProps) {
  const [uploadingIndex, setUploadingIndex] = useState<number | null>(null);

  if (loading) {
    return <div className="hciot-merged-csv-loading">{language === 'zh' ? '載入整合資料中...' : 'Loading merged data...'}</div>;
  }

  if (error) {
    return <div className="hciot-merged-csv-error">{error}</div>;
  }

  if (rows.length === 0 && !isEditing) {
    return <div className="hciot-merged-csv-empty">{language === 'zh' ? '此主題目前沒有 CSV 檔案。' : 'No CSV files found for this topic.'}</div>;
  }

  const handleFileChange = async (index: number, file: File | null) => {
    if (!file || !onUploadImage) return;
    setUploadingIndex(index);
    try {
      const res = await onUploadImage(file);
      onUpdateRow(index, { img: res.image_id });
    } catch (err) {
      console.error('Failed to upload image:', err);
      alert(language === 'zh' ? '圖片上傳失敗' : 'Failed to upload image');
    } finally {
      setUploadingIndex(null);
    }
  };

  return (
    <div className="hciot-merged-csv-container">
      <div className="hciot-merged-csv-meta">
        {language === 'zh' ? `已合併 ${sourceFiles.length} 個檔案` : `Merged ${sourceFiles.length} files`}
      </div>
      <div className="hciot-merged-csv-table-wrapper">
        <table className="hciot-merged-csv-table">
          <thead>
            <tr>
              <th style={{ width: '60px' }}>{language === 'zh' ? '編號' : 'Index'}</th>
              <th>{language === 'zh' ? '問題 (Q)' : 'Question (Q)'}</th>
              <th>{language === 'zh' ? '回答 (A)' : 'Answer (A)'}</th>
              <th style={{ width: '120px' }}>{language === 'zh' ? '圖片 (IMG)' : 'Image (IMG)'}</th>
              {isEditing && <th style={{ width: '60px', textAlign: 'center' }}>-</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const imageUrl = getHciotImageUrl(row.img);
              return (
                <tr key={`${row.index}-${i}`}>
                  <td>{i + 1}</td>
                  <td>
                    {isEditing ? (
                      <textarea
                        className="hciot-file-textarea"
                        style={{ minHeight: '60px', padding: '4px' }}
                        value={row.q}
                        onChange={(e) => onUpdateRow(i, { q: e.target.value })}
                      />
                    ) : (
                      row.q
                    )}
                  </td>
                  <td style={{ whiteSpace: 'pre-wrap' }}>
                    {isEditing ? (
                      <textarea
                        className="hciot-file-textarea"
                        style={{ minHeight: '60px', padding: '4px' }}
                        value={row.a}
                        onChange={(e) => onUpdateRow(i, { a: e.target.value })}
                      />
                    ) : (
                      row.a
                    )}
                  </td>
                  <td>
                    {isEditing ? (
                      <div className="hciot-merged-csv-img-cell">
                        {row.img ? (
                          <div className="hciot-merged-csv-img-wrapper edit-mode">
                            {imageUrl && (
                              <img src={imageUrl} alt={row.img} className="hciot-merged-csv-thumbnail" />
                            )}
                            <button
                              type="button"
                              className="hciot-merged-csv-remove-img"
                              onClick={() => onUpdateRow(i, { img: '' })}
                              title={language === 'zh' ? '移除圖片' : 'Remove image'}
                            >
                              <X size={12} />
                            </button>
                            <span className="hciot-merged-csv-img-text">{normalizeImageId(row.img)}</span>
                          </div>
                        ) : (
                          <label className={`hciot-merged-csv-upload-btn${uploadingIndex === i ? ' is-uploading' : ''}`}>
                            <input
                              type="file"
                              accept="image/*"
                              style={{ display: 'none' }}
                              onChange={(e) => handleFileChange(i, e.target.files?.[0] || null)}
                              disabled={uploadingIndex === i}
                            />
                            <Upload size={14} />
                            <span>{uploadingIndex === i ? '...' : (language === 'zh' ? '上傳' : 'Upload')}</span>
                          </label>
                        )}
                      </div>
                    ) : row.img ? (
                      <div className="hciot-merged-csv-img-wrapper">
                        {imageUrl && (
                          <img
                            src={imageUrl}
                            alt={row.img}
                            className="hciot-merged-csv-thumbnail"
                            title={row.img}
                            onError={(e) => {
                              (e.target as HTMLImageElement).style.display = 'none';
                              const next = (e.target as HTMLImageElement).nextElementSibling;
                              if (next) next.classList.remove('hidden');
                            }}
                          />
                        )}
                        <span className="hciot-merged-csv-img-text hidden">{row.img}</span>
                      </div>
                    ) : null}
                  </td>
                  {isEditing && (
                    <td style={{ textAlign: 'center' }}>
                      <button
                        type="button"
                        className="hciot-explorer-icon-button danger"
                        onClick={() => onDeleteRow(i)}
                        title={language === 'zh' ? '刪除此列' : 'Delete row'}
                      >
                        <Trash2 size={15} />
                      </button>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
        {isEditing && (
          <div style={{ marginTop: '1rem', textAlign: 'center' }}>
            <button
              type="button"
              className="hciot-file-action-button"
              onClick={onAddRow}
            >
              <Plus size={15} />
              <span>{language === 'zh' ? '新增 Q&A' : 'Add Q&A'}</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}