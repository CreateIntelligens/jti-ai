import { Trash2, Image as ImageIcon } from 'lucide-react';
import type { HciotLanguage } from '../../../../config/hciotTopics';
import type { HciotImage } from '../../../../services/api/hciot';

interface ImageDetailPaneProps {
  language: HciotLanguage;
  selectedImage: HciotImage | null;
  deleting: boolean;
  cleaningUnused: boolean;
  unusedImageCount: number;
  onDelete: () => void;
  onCleanupUnused: () => void;
}

export default function ImageDetailPane({
  language: _language,
  selectedImage,
  deleting,
  cleaningUnused,
  unusedImageCount,
  onDelete,
  onCleanupUnused,
}: ImageDetailPaneProps) {
  if (!selectedImage) {
    return (
      <div className="hciot-file-editor">
        <div className="hciot-file-empty">
          <ImageIcon size={28} />
          <div>
            <h3>從左側檔案樹選擇圖片</h3>
            <p>在右側預覽圖片並查看詳細資訊</p>
          </div>
        </div>
      </div>
    );
  }

  const referenceCount = selectedImage.reference_count ?? 0;
  const isReferenced = referenceCount > 0;
  const referenceLabel = isReferenced
    ? `被 ${referenceCount} 題引用`
    : '未被任何題目引用';
  const referenceColor = isReferenced ? '#166534' : '#b45309';

  return (
    <div className="hciot-file-editor hciot-image-detail-pane">
      <div className="hciot-file-header">
        <div>
          <p className="hciot-file-kicker">知識庫</p>
          <h2 className="hciot-file-title">{selectedImage.image_id}</h2>
          <p className="hciot-file-path">圖片目錄</p>
        </div>

        <div className="hciot-file-actions">
          <button
            type="button"
            className="hciot-file-action-button"
            onClick={onCleanupUnused}
            disabled={cleaningUnused || unusedImageCount === 0}
          >
            <span>
              {cleaningUnused
                ? '清理中...'
                : `清理未引用圖片 (${unusedImageCount})`}
            </span>
          </button>
          <button
            type="button"
            className="hciot-file-action-button danger"
            onClick={onDelete}
            disabled={deleting}
          >
            <Trash2 size={15} />
            <span>{deleting ? '刪除中...' : '刪除'}</span>
          </button>
        </div>
      </div>

      <section className="hciot-file-editor-panel hciot-image-preview-panel">
        <div className="hciot-file-editor-meta hciot-image-preview-meta-full">
          <span>ID: {selectedImage.image_id}</span>
          <span>{selectedImage.size_bytes ? `${Math.max(1, Math.round(selectedImage.size_bytes / 1024))} KB` : '0 KB'}</span>
          <span style={{ color: referenceColor, fontWeight: 600 }}>{referenceLabel}</span>
        </div>
        <div className="hciot-image-preview-container">
          <img className="hciot-image-preview-img" src={selectedImage.url} alt={selectedImage.image_id} />
        </div>
      </section>
    </div>
  );
}
