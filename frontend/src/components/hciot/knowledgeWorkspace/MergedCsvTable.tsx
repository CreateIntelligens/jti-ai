import { Plus, Trash2 } from 'lucide-react';
import type { HciotMergedCsvRow } from '../../../services/api/hciot';
import type { HciotLanguage } from '../../../config/hciotTopics';

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
}: MergedCsvTableProps) {
  if (loading) {
    return <div className="hciot-merged-csv-loading">{language === 'zh' ? '載入整合資料中...' : 'Loading merged data...'}</div>;
  }

  if (error) {
    return <div className="hciot-merged-csv-error">{error}</div>;
  }

  if (rows.length === 0 && !isEditing) {
    return <div className="hciot-merged-csv-empty">{language === 'zh' ? '此主題目前沒有 CSV 檔案。' : 'No CSV files found for this topic.'}</div>;
  }

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
            {rows.map((row, i) => (
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
                    <input
                      className="hciot-file-input"
                      value={row.img || ''}
                      placeholder="image.jpg"
                      onChange={(e) => onUpdateRow(i, { img: e.target.value })}
                    />
                  ) : row.img ? (
                    <div className="hciot-merged-csv-img-wrapper">
                      <img
                        src={`/api/hciot/images/${row.img.replace(/\.[^.]+$/, '')}`}
                        alt={row.img}
                        className="hciot-merged-csv-thumbnail"
                        title={row.img}
                        onError={(e) => {
                          (e.target as HTMLImageElement).style.display = 'none';
                          const next = (e.target as HTMLImageElement).nextElementSibling;
                          if (next) next.classList.remove('hidden');
                        }}
                      />
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
            ))}
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