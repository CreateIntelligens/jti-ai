import { useState } from 'react';
import type { QaImage } from '../../../../services/api/_shared/qaKnowledge';
import type { QaWorkspaceApiClient } from '../QaKnowledgeWorkspace';
import { getErrorMessage } from '../topicUtils';

export interface UseImageManagementOptions {
  api: QaWorkspaceApiClient;
  selectedImage: QaImage | null;
  selectedImageName: string | null;
  setSelectedImageName: (name: string | null) => void;
  unusedImageCount: number;
  refreshWorkspace: () => Promise<void>;
  completeUpload: (firstUploadedFileName: string | null, message: string) => Promise<void>;
  showStatus: (message: string) => void;
  text: (zh: string, en: string) => string;
}

export function useImageManagement({
  api,
  selectedImage,
  selectedImageName,
  setSelectedImageName,
  unusedImageCount,
  refreshWorkspace,
  completeUpload,
  showStatus,
  text,
}: UseImageManagementOptions) {
  const [deleting, setDeleting] = useState(false);
  const [cleaningUnusedImages, setCleaningUnusedImages] = useState(false);

  const handleDeleteImage = async () => {
    if (!selectedImage) return;
    const referenceCount = selectedImage.reference_count ?? 0;
    let confirmMessage = text(
      `確定要刪除圖片 ${selectedImage.image_id}？`,
      `Delete image ${selectedImage.image_id}?`,
    );
    if (referenceCount > 0) {
      confirmMessage = text(
        `圖片 ${selectedImage.image_id} 目前被 ${referenceCount} 題引用，刪除後相關回答將無法顯示圖片。確定要刪除嗎？`,
        `Image ${selectedImage.image_id} is still referenced by ${referenceCount} item(s). Delete it anyway?`,
      );
    }
    const confirmed = window.confirm(confirmMessage);
    if (!confirmed) return;

    setDeleting(true);
    try {
      await api.deleteImage(selectedImage.image_id);
      await refreshWorkspace();
      setSelectedImageName(null);
      showStatus(text('圖片已刪除', 'Image deleted'));
    } catch (error) {
      console.error('Failed to delete image:', error);
      alert(getErrorMessage(error));
    } finally {
      setDeleting(false);
    }
  };

  const handleCleanupUnusedImages = async () => {
    if (unusedImageCount === 0) return;

    const confirmed = window.confirm(text(
      `確定要刪除 ${unusedImageCount} 張未被任何題目引用的圖片？`,
      `Delete ${unusedImageCount} unused image(s)?`,
    ));
    if (!confirmed) return;

    setCleaningUnusedImages(true);
    try {
      const response = await api.deleteUnusedImages();
      await refreshWorkspace();
      if (selectedImageName && response.deleted_image_ids.includes(selectedImageName)) {
        setSelectedImageName(null);
      }
      showStatus(text(
        `已刪除 ${response.deleted_count} 張未引用圖片`,
        `Deleted ${response.deleted_count} unused image(s)`,
      ));
    } catch (error) {
      console.error('Failed to clean unused images:', error);
      alert(getErrorMessage(error));
    } finally {
      setCleaningUnusedImages(false);
    }
  };

  const handleUploadImageComplete = async (count: number) => {
    await completeUpload(null, text(
      `已上傳 ${count} 張圖片`,
      `Uploaded ${count} image(s)`,
    ));
  };

  return {
    deleting,
    setDeleting,
    cleaningUnusedImages,
    handleDeleteImage,
    handleCleanupUnusedImages,
    handleUploadImageComplete,
  };
}
