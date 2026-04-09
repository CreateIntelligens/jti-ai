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
  language,
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
            <h3>{language === 'zh' ? '從左側 Explorer 選擇圖片' : 'Select an image from the Explorer'}</h3>
            <p>{language === 'zh' ? '在右側預覽圖片並查看詳細資訊' : 'Preview the image and view details here.'}</p>
          </div>
        </div>
      </div>
    );
  }

  const referenceCount = selectedImage.reference_count ?? 0;
  const isReferenced = referenceCount > 0;
  const referenceLabel = isReferenced
    ? (language === 'zh' ? `被 ${referenceCount} 題引用` : `Referenced by ${referenceCount} item(s)`)
    : (language === 'zh' ? '未被任何題目引用' : 'Unused');
  const referenceColor = isReferenced ? '#166534' : '#b45309';

  return (
    <div className="hciot-file-editor hciot-image-detail-pane">
      <div className="hciot-file-header">
        <div>
          <p className="hciot-file-kicker">Knowledge Explorer</p>
          <h2 className="hciot-file-title">{selectedImage.image_id}</h2>
          <p className="hciot-file-path">{language === 'zh' ? '圖片目錄' : 'Images'}</p>
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
                ? (language === 'zh' ? '清理中...' : 'Cleaning...')
                : (language === 'zh' ? `清理未引用圖片 (${unusedImageCount})` : `Clean Unused (${unusedImageCount})`)}
            </span>
          </button>
          <button
            type="button"
            className="hciot-file-action-button danger"
            onClick={onDelete}
            disabled={deleting}
          >
            <Trash2 size={15} />
            <span>{deleting ? (language === 'zh' ? '刪除中...' : 'Deleting...') : (language === 'zh' ? '刪除' : 'Delete')}</span>
          </button>
        </div>
      </div>

      <section className="hciot-file-editor-panel hciot-image-preview-panel" style={{ display: 'flex', flexDirection: 'column', gap: '16px', alignItems: 'center', justifyContent: 'center' }}>
        <div className="hciot-file-editor-meta" style={{ width: '100%' }}>
          <span>ID: {selectedImage.image_id}</span>
          <span>{selectedImage.size_bytes ? `${Math.max(1, Math.round(selectedImage.size_bytes / 1024))} KB` : '0 KB'}</span>
          <span style={{ color: referenceColor, fontWeight: 600 }}>{referenceLabel}</span>
        </div>
        <div className="hciot-image-preview-container" style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#f3f4f6', borderRadius: '8px', overflow: 'hidden', width: '100%', minHeight: '300px' }}>
          <img
            src={selectedImage.url}
            alt={selectedImage.image_id}
            style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }}
          />
        </div>
      </section>
    </div>
  );
}
