import { Plus, Trash2 } from 'lucide-react';
import type { HciotQaPair } from '../../../../services/api/hciot';

interface QaEditPreviewProps {
  qaPairs: HciotQaPair[];
  onChange: (pairs: HciotQaPair[]) => void;
  language: string;
}

export default function QaEditPreview({ qaPairs, onChange, language: _language }: QaEditPreviewProps) {
  const handleUpdate = (index: number, field: 'q' | 'a', value: string) => {
    const updated = [...qaPairs];
    updated[index] = {
      ...updated[index],
      [field]: value,
    };
    onChange(updated);
  };

  const handleRemove = (index: number) => {
    const updated = qaPairs.filter((_, idx) => idx !== index);
    onChange(updated);
  };

  const handleAdd = () => {
    onChange([...qaPairs, { q: '', a: '' }]);
  };

  return (
    <div className="hciot-qa-edit-preview">
      <div className="hciot-qa-preview-header">
        <h4 className="hciot-qa-preview-title">
          從文件擷取了 {qaPairs.length} 組問答對
        </h4>
        <p className="hciot-qa-preview-subtitle">
          匯入後這些問答將預設不顯示（可透過 RAG 搜尋檢索，但不會出現在側欄快速問答按鈕）。
        </p>
      </div>

      <div className="hciot-qa-preview-list custom-scrollbar">
        {qaPairs.map((pair, index) => (
          <div key={index} className="hciot-qa-preview-card">
            <div className="hciot-qa-card-badge">問答 {index + 1}</div>
            <div className="hciot-qa-card-fields">
              <div className="hciot-qa-field-group">
                <span className="hciot-qa-field-tag q">Q</span>
                <textarea
                  className="hciot-qa-preview-textarea q"
                  placeholder="請輸入問題 (Q)"
                  value={pair.q}
                  onChange={(event) => handleUpdate(index, 'q', event.target.value)}
                  rows={2}
                />
              </div>
              <div className="hciot-qa-field-group">
                <span className="hciot-qa-field-tag a">A</span>
                <textarea
                  className="hciot-qa-preview-textarea a"
                  placeholder="請輸入回答 (A)"
                  value={pair.a}
                  onChange={(event) => handleUpdate(index, 'a', event.target.value)}
                  rows={4}
                />
              </div>
            </div>
            <button
              type="button"
              className="hciot-qa-card-delete"
              onClick={() => handleRemove(index)}
              title="刪除此組問答"
              aria-label="刪除"
            >
              <Trash2 size={16} />
            </button>
          </div>
        ))}
      </div>

      <button
        type="button"
        className="hciot-qa-preview-add"
        onClick={handleAdd}
      >
        <Plus size={16} />
        <span>手動新增一組問答</span>
      </button>
    </div>
  );
}
