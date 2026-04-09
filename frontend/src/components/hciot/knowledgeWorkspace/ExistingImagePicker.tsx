import { useEffect, useMemo, useState } from 'react';
import { Image as ImageIcon, Search, X } from 'lucide-react';

import type { HciotLanguage } from '../../../config/hciotTopics';
import type { HciotImage } from '../../../services/api/hciot';

interface ExistingImagePickerProps {
  open: boolean;
  language: HciotLanguage;
  images: HciotImage[];
  selectedImageId?: string | null;
  onClose: () => void;
  onSelect: (imageId: string) => void;
}

function imageReferenceLabel(language: HciotLanguage, image: HciotImage): string {
  const count = image.reference_count ?? 0;
  return count > 0
    ? (language === 'zh' ? `被 ${count} 題引用` : `Referenced by ${count} item(s)`)
    : (language === 'zh' ? '未引用' : 'Unused');
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

  useEffect(() => {
    if (!open) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose, open]);

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
      <section style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <h4 style={{ margin: 0, fontSize: 13, fontWeight: 700, color: '#334155' }}>{title}</h4>
        <div style={{ display: 'grid', gap: 10 }}>
          {sectionImages.map((image) => {
            const isSelected = selectedImageId === image.image_id;
            const isUnused = (image.reference_count ?? 0) === 0;
            return (
              <button
                key={image.image_id}
                type="button"
                onClick={() => onSelect(image.image_id)}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '72px 1fr',
                  gap: 12,
                  alignItems: 'center',
                  textAlign: 'left',
                  borderRadius: 12,
                  border: isSelected ? '2px solid #2563eb' : '1px solid #dbe4ee',
                  background: '#fff',
                  padding: 10,
                  cursor: 'pointer',
                  boxShadow: isSelected ? '0 0 0 2px rgba(37, 99, 235, 0.08)' : 'none',
                }}
              >
                <div style={{
                  width: 72,
                  height: 72,
                  borderRadius: 10,
                  background: '#f8fafc',
                  overflow: 'hidden',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  border: '1px solid #e2e8f0',
                }}>
                  <img
                    src={image.url}
                    alt={image.image_id}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                </div>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 700, color: '#0f172a', wordBreak: 'break-word' }}>{image.image_id}</div>
                  <div style={{ marginTop: 4, fontSize: 12, color: isUnused ? '#b45309' : '#166534' }}>
                    {imageReferenceLabel(language, image)}
                  </div>
                  <div style={{ marginTop: 4, fontSize: 12, color: '#64748b' }}>
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
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1000,
        background: 'rgba(15, 23, 42, 0.45)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: 'min(880px, 100%)',
          maxHeight: 'min(80vh, 860px)',
          overflow: 'hidden',
          background: '#ffffff',
          borderRadius: 18,
          boxShadow: '0 30px 80px rgba(15, 23, 42, 0.28)',
          display: 'flex',
          flexDirection: 'column',
        }}
        onClick={(event) => event.stopPropagation()}
      >
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '18px 20px 14px',
          borderBottom: '1px solid #e2e8f0',
        }}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 800, color: '#0f172a' }}>
              {language === 'zh' ? '選擇既有圖片' : 'Select Existing Image'}
            </div>
            <div style={{ marginTop: 4, fontSize: 13, color: '#64748b' }}>
              {language === 'zh' ? '未引用圖片會優先顯示在上方' : 'Unused images are listed first.'}
            </div>
          </div>
          <button type="button" className="hciot-explorer-icon-button" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <div style={{ padding: 16, borderBottom: '1px solid #e2e8f0' }}>
          <label style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            border: '1px solid #cbd5e1',
            borderRadius: 12,
            padding: '10px 12px',
            background: '#f8fafc',
          }}>
            <Search size={16} color="#64748b" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={language === 'zh' ? '搜尋 image id' : 'Search image id'}
              style={{
                border: 0,
                outline: 'none',
                background: 'transparent',
                width: '100%',
                fontSize: 14,
                color: '#0f172a',
              }}
            />
          </label>
        </div>

        <div style={{ padding: 16, overflowY: 'auto', display: 'grid', gap: 18 }}>
          {filteredImages.length === 0 ? (
            <div style={{
              minHeight: 220,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 10,
              color: '#64748b',
            }}>
              <ImageIcon size={24} />
              <div>{language === 'zh' ? '找不到符合條件的圖片' : 'No matching images found'}</div>
            </div>
          ) : (
            <>
              {renderSection(language === 'zh' ? '未引用圖片' : 'Unused', unusedImages)}
              {renderSection(language === 'zh' ? '其他圖片' : 'Referenced', referencedImages)}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
