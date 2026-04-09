import { useEffect, useRef, useState } from 'react';
import { Image as ImageIcon, X } from 'lucide-react';

import type { HciotLanguage } from '../../../../config/hciotTopics';
import { usePendingImageUrls, type UploadedImageResult } from '../imageUpload';
import UploadStatusIcon from './UploadStatusIcon';
import UploadTabBody from './UploadTabBody';
import type { ImageItem } from './types';

interface ImageUploadTabProps {
  open: boolean;
  language: HciotLanguage;
  onClose: () => void;
  onUploadImage: (file: File, imageId?: string) => Promise<UploadedImageResult>;
  onUploadImageComplete: (count: number) => Promise<void>;
}

export default function ImageUploadTab({
  open,
  language,
  onClose,
  onUploadImage,
  onUploadImageComplete,
}: ImageUploadTabProps) {
  const [dragOver, setDragOver] = useState(false);
  const [selectedImages, setSelectedImages] = useState<ImageItem[]>([]);
  const [uploadingLocal, setUploadingLocal] = useState(false);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const selectedImageUrls = usePendingImageUrls(
    selectedImages.map((item) => ({ pendingImageFile: item.file })),
  );

  useEffect(() => {
    if (open) {
      setDragOver(false);
      setSelectedImages([]);
      setUploadingLocal(false);
    }
  }, [open]);

  const canSubmitImage = selectedImages.some((item) => item.status === 'pending' || item.status === 'error')
    && !uploadingLocal;

  const handleImageSelect = (fileList: FileList | null) => {
    if (!fileList?.length) {
      return;
    }

    const newFiles = Array.from(fileList)
      .filter((file) => file.type.startsWith('image/'))
      .map((file) => ({ file, imageId: '', status: 'pending' as const }));
    setSelectedImages((previous) => [...previous, ...newFiles]);

    if (imageInputRef.current) {
      imageInputRef.current.value = '';
    }
  };

  const updateImageStatus = (index: number, updates: Partial<ImageItem>) => {
    setSelectedImages((previous) => previous.map((image, imageIndex) => (
      imageIndex === index ? { ...image, ...updates } : image
    )));
  };

  const handleUploadImages = async () => {
    const pendingImages = selectedImages
      .map((item, index) => ({ item, index }))
      .filter(({ item }) => item.status === 'pending' || item.status === 'error');
    if (!pendingImages.length) {
      return;
    }

    setUploadingLocal(true);
    let successCount = 0;

    for (const { item, index } of pendingImages) {
      updateImageStatus(index, { status: 'uploading' });

      try {
        await onUploadImage(item.file, item.imageId.trim() || undefined);
        successCount += 1;
        updateImageStatus(index, { status: 'done', error: undefined });
      } catch (error: any) {
        updateImageStatus(index, { status: 'error', error: error.message || String(error) });
      }
    }

    setUploadingLocal(false);
    if (successCount > 0) {
      await onUploadImageComplete(successCount);
    }
  };

  return (
    <UploadTabBody
      language={language}
      dragOver={dragOver}
      setDragOver={setDragOver}
      inputRef={imageInputRef}
      items={selectedImages}
      isUploading={uploadingLocal}
      disabled={!canSubmitImage}
      accept="image/*"
      dropLabelZh="點擊或拖放圖片檔案"
      dropLabelEn="Click or drop image files here"
      dropSubZh="支援 JPG、PNG、GIF、WEBP (最大 10MB)"
      dropSubEn="JPG, PNG, GIF, WEBP (Max 10MB)"
      countZh="張圖片"
      countEn="image(s)"
      listStyle={{ maxHeight: '300px', overflowY: 'auto' }}
      onDrop={(event) => {
        event.preventDefault();
        setDragOver(false);
        if (event.dataTransfer.files.length) {
          handleImageSelect(event.dataTransfer.files);
        }
      }}
      onSelect={handleImageSelect}
      onUpload={() => { void handleUploadImages(); }}
      onClose={onClose}
      renderItem={(item, index) => {
        const previewUrl = selectedImageUrls.get(item.file) || '';

        return (
          <div key={`${item.file.name}-${index}`} className="hciot-upload-file-item image-item">
            {previewUrl ? (
              <img src={previewUrl} alt={item.imageId.trim() || item.file.name} className="hciot-upload-image-thumb" />
            ) : (
              <ImageIcon size={16} className="hciot-icon-green" />
            )}
            <div className="hciot-upload-image-info">
              <span className="hciot-upload-file-name">{item.file.name}</span>
              <input
                type="text"
                placeholder={language === 'zh' ? '自訂 IMG ID (選填)' : 'Custom IMG ID (optional)'}
                value={item.imageId}
                onChange={(event) => setSelectedImages((previous) => previous.map((image, imageIndex) => (
                  imageIndex === index ? { ...image, imageId: event.target.value } : image
                )))}
                disabled={item.status === 'uploading' || item.status === 'done'}
                className="hciot-file-input hciot-upload-image-id-input"
              />
            </div>
            <span className="hciot-upload-file-size">
              {item.file.size > 1024 ? `${(item.file.size / 1024).toFixed(1)} KB` : `${item.file.size} B`}
            </span>
            <div className="hciot-file-actions">
              <UploadStatusIcon status={item.status} error={item.error} />
              {item.status !== 'uploading' && item.status !== 'done' && (
                <button
                  type="button"
                  className="hciot-qa-row-delete"
                  onClick={() => setSelectedImages((previous) => previous.filter((_, imageIndex) => imageIndex !== index))}
                  title={language === 'zh' ? '移除' : 'Remove'}
                >
                  <X size={14} />
                </button>
              )}
            </div>
          </div>
        );
      }}
    />
  );
}
