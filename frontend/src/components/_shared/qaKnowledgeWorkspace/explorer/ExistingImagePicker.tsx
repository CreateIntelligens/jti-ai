import { useEffect, useMemo, useState } from 'react';
import { useEscapeKey } from '../../../../hooks/useEscapeKey';
import { Image as ImageIcon, Search, X } from 'lucide-react';

import type { HciotLanguage } from '../../../../config/hciotTopics';
import type { HciotImage } from '../../../../services/api/hciot';

interface ExistingImagePickerProps {
  open: boolean;
  language: HciotLanguage;
  images: HciotImage[];
  selectedImageId?: string | null;
  onClose: () => void;
  onSelect: (imageId: string) => void;
}

function imageReferenceLabel(_language: HciotLanguage, image: HciotImage): string {
  const count = image.reference_count ?? 0;
  return count > 0
    ? `被 ${count} 題引用`
    : '未引用';
}

export default function ExistingImagePicker({
  open,
  language,
  images,
  selectedImageId,
  onClose,
  onSelect,
}: ExistingImagePickerProps) {
  const [query, setQuery] = useState('');

  useEffect(() => {
    if (open) {
      setQuery('');
    }
  }, [open]);

  useEscapeKey(onClose, open);

  const normalizedQuery = query.trim().toLowerCase();
  const filteredImages = useMemo(() => {
    const matches = images.filter((image) => (
      !normalizedQuery
      || image.image_id.toLowerCase().includes(normalizedQuery)
    ));

    return matches.sort((left, right) => {
      const leftUnused = (left.reference_count ?? 0) === 0 ? 0 : 1;
      const rightUnused = (right.reference_count ?? 0) === 0 ? 0 : 1;
      if (leftUnused !== rightUnused) {
        return leftUnused - rightUnused;
      }
      return left.image_id.localeCompare(right.image_id, undefined, { numeric: true, sensitivity: 'base' });
    });
  }, [images, normalizedQuery]);

  const unusedImages = filteredImages.filter((image) => (image.reference_count ?? 0) === 0);
  const referencedImages = filteredImages.filter((image) => (image.reference_count ?? 0) > 0);

  if (!open) {
    return null;
  }

  const renderSection = (title: string, sectionImages: HciotImage[]) => {
    if (!sectionImages.length) {
      return null;
    }

    return (
      <section className="qa-workspace-image-picker-section">
        <h4 className="qa-workspace-image-picker-section-title">{title}</h4>
        <div className="qa-workspace-image-picker-grid">
          {sectionImages.map((image) => {
            const isSelected = selectedImageId === image.image_id;
            const isUnused = (image.reference_count ?? 0) === 0;
            return (
              <button
                key={image.image_id}
                type="button"
                className={`qa-workspace-image-picker-card${isSelected ? ' is-selected' : ''}`}
                onClick={() => onSelect(image.image_id)}
              >
                <div className="qa-workspace-image-picker-thumb-wrapper">
                  <img
                    src={image.url}
                    alt={image.image_id}
                    className="qa-workspace-image-picker-thumb"
                  />
                </div>
                <div className="qa-workspace-image-picker-info">
                  <div className="qa-workspace-image-picker-id">{image.image_id}</div>
                  <div className={`qa-workspace-image-picker-ref${isUnused ? ' is-unused' : ''}`}>
                    {imageReferenceLabel(language, image)}
                  </div>
                  <div className="qa-workspace-image-picker-size">
                    {image.size_bytes ? `${Math.max(1, Math.round(image.size_bytes / 1024))} KB` : '0 KB'}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </section>
    );
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="qa-workspace-image-picker-overlay"
      onClick={onClose}
    >
      <div
        className="qa-workspace-image-picker-dialog"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="qa-workspace-image-picker-header">
          <div>
            <div className="qa-workspace-image-picker-title">
              選擇既有圖片
            </div>
            <div className="qa-workspace-image-picker-subtitle">
              未引用圖片會優先顯示在上方
            </div>
          </div>
          <button type="button" className="qa-workspace-explorer-icon-button" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <div className="qa-workspace-image-picker-search">
          <label className="qa-workspace-image-picker-search-label">
            <Search size={16} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜尋 image id"
              className="qa-workspace-image-picker-search-input"
            />
          </label>
        </div>

        <div className="qa-workspace-image-picker-body custom-scrollbar">
          {filteredImages.length === 0 ? (
            <div className="qa-workspace-image-picker-empty">
              <ImageIcon size={24} />
              <div>找不到符合條件的圖片</div>
            </div>
          ) : (
            <>
              {renderSection('未引用圖片', unusedImages)}
              {renderSection('其他圖片', referencedImages)}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
