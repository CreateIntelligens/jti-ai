import { useState } from 'react';
import { Image as ImageIcon, Loader2, Plus, Trash2, Upload, X } from 'lucide-react';
import type { HciotImage, HciotMergedCsvRow } from '../../../../services/api/hciot';
import type { HciotLanguage } from '../../../../config/hciotTopics';
import { getHciotImageUrl, normalizeImageId } from '../../../../utils/hciotImage';
import ExistingImagePicker from '../explorer/ExistingImagePicker';
import { usePendingImageUrls } from '../imageUpload';
import type { FileStatus } from '../upload/types';

export interface EditableMergedCsvRow extends HciotMergedCsvRow {
  pendingImageFile?: File | null;
  pendingImageName?: string;
  imgStatus?: FileStatus;
  imgError?: string;
}

function clearRowImageState(): Partial<EditableMergedCsvRow> {
  return {
    img: '',
    pendingImageFile: undefined,
    pendingImageName: undefined,
    imgStatus: 'pending',
    imgError: undefined,
  };
}

function applyExistingRowImage(imageId: string): Partial<EditableMergedCsvRow> {
  return {
    ...clearRowImageState(),
    img: imageId,
    imgStatus: 'done',
  };
}

interface MergedCsvTableProps {
  language: HciotLanguage;
  rows: EditableMergedCsvRow[];
  sourceFiles: string[];
  availableImages: HciotImage[];
  loading: boolean;
  error: string | null;
  isEditing: boolean;
  onUpdateRow: (index: number, updated: Partial<EditableMergedCsvRow>) => void;
  onDeleteRow: (index: number) => void;
  onAddRow: () => void;
}

export default function MergedCsvTable({
  language,
  rows,
  sourceFiles,
  availableImages,
  loading,
  error,
  isEditing,
  onUpdateRow,
  onDeleteRow,
  onAddRow,
}: MergedCsvTableProps) {
  const pendingUrls = usePendingImageUrls(rows);
  const [pickerIndex, setPickerIndex] = useState<number | null>(null);

  if (loading) {
    return <div className="hciot-merged-csv-loading">載入整合資料中...</div>;
  }

  if (error) {
    return <div className="hciot-merged-csv-error">{error}</div>;
  }

  if (rows.length === 0 && !isEditing) {
    return <div className="hciot-merged-csv-empty">此主題目前沒有 CSV 檔案。</div>;
  }

  const handleFileChange = (index: number, file: File | null) => {
    if (!file || !file.type.startsWith('image/')) return;
    onUpdateRow(index, {
      img: '',
      pendingImageFile: file,
      pendingImageName: file.name,
      imgStatus: 'pending',
      imgError: undefined,
    });
  };

  const handleSelectExistingImage = (imageId: string) => {
    if (pickerIndex === null) {
      return;
    }

    const rowIndex = pickerIndex;
    setPickerIndex(null);
    onUpdateRow(rowIndex, applyExistingRowImage(imageId));
  };

  return (
    <div className="hciot-merged-csv-container">
      <ExistingImagePicker
        open={pickerIndex !== null}
        language={language}
        images={availableImages}
        selectedImageId={pickerIndex === null ? null : (rows[pickerIndex]?.img || null)}
        onClose={() => setPickerIndex(null)}
        onSelect={handleSelectExistingImage}
      />
      <div className="hciot-merged-csv-meta">
        {`已合併 ${sourceFiles.length} 個檔案`}
      </div>
      <div className="hciot-merged-csv-table-wrapper">
        <table className="hciot-merged-csv-table">
          <thead>
            <tr>
              <th style={{ width: '60px' }}>編號</th>
              <th>問題 (Q)</th>
              <th>回答 (A)</th>
              <th style={{ width: '180px' }}>圖片 (IMG)</th>
              <th style={{ width: '180px' }}>網址 (URL)</th>
              {isEditing && <th style={{ width: '60px', textAlign: 'center' }}>-</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const hasPendingImage = Boolean(row.pendingImageFile);
              const hasImage = Boolean(row.img || hasPendingImage);
              const imageUrl = hasPendingImage
                ? (row.pendingImageFile ? pendingUrls.get(row.pendingImageFile) || '' : '')
                : getHciotImageUrl(row.img);
              const imageLabel = row.pendingImageName || normalizeImageId(row.img) || row.img;
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
                        {hasImage ? (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                            <div className="hciot-merged-csv-img-wrapper edit-mode">
                              {imageUrl && (
                                <img src={imageUrl} alt={row.img} className="hciot-merged-csv-thumbnail" />
                              )}
                              {row.imgStatus === 'uploading' ? (
                                <Loader2 size={14} className="animate-spin" />
                              ) : null}
                              <button
                                type="button"
                                className="hciot-merged-csv-remove-img"
                                onClick={() => onUpdateRow(i, clearRowImageState())}
                                title="移除圖片"
                              >
                                <X size={12} />
                              </button>
                              <span className="hciot-merged-csv-img-text" title={row.imgError || imageLabel}>{imageLabel}</span>
                            </div>
                            <div style={{ display: 'flex', gap: 6 }}>
                              <label className={`hciot-merged-csv-upload-btn${row.imgStatus === 'uploading' ? ' is-uploading' : ''}`}>
                                <input
                                  type="file"
                                  accept="image/*"
                                  style={{ display: 'none' }}
                                  onChange={(e) => handleFileChange(i, e.target.files?.[0] || null)}
                                  disabled={row.imgStatus === 'uploading'}
                                />
                                <Upload size={14} />
                              </label>
                              <button
                                type="button"
                                className="hciot-merged-csv-upload-btn"
                                onClick={() => setPickerIndex(i)}
                              >
                                <ImageIcon size={14} />
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div style={{ display: 'flex', gap: 6 }}>
                            <label className={`hciot-merged-csv-upload-btn${row.imgStatus === 'uploading' ? ' is-uploading' : ''}`}>
                              <input
                                type="file"
                                accept="image/*"
                                style={{ display: 'none' }}
                                onChange={(e) => handleFileChange(i, e.target.files?.[0] || null)}
                                disabled={row.imgStatus === 'uploading'}
                              />
                              <Upload size={14} />
                              <span>{row.imgStatus === 'uploading' ? '...' : '上傳'}</span>
                            </label>
                            <button
                              type="button"
                              className="hciot-merged-csv-upload-btn"
                              onClick={() => setPickerIndex(i)}
                            >
                              <ImageIcon size={14} />
                              <span>既有</span>
                            </button>
                          </div>
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
                  <td style={{ wordBreak: 'break-all' }}>
                    {isEditing ? (
                      <textarea
                        className="hciot-file-textarea"
                        style={{ minHeight: '60px', padding: '4px' }}
                        value={row.url || ''}
                        onChange={(e) => onUpdateRow(i, { url: e.target.value })}
                      />
                    ) : row.url ? (
                      <a href={row.url} target="_blank" rel="noopener noreferrer">{row.url}</a>
                    ) : null}
                  </td>
                  {isEditing && (
                    <td style={{ textAlign: 'center' }}>
                      <button
                        type="button"
                        className="hciot-explorer-icon-button danger"
                        onClick={() => onDeleteRow(i)}
                        title="刪除此列"
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
              <span>新增 Q&A</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
