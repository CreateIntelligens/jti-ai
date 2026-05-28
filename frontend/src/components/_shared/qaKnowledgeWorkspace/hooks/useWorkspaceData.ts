import { useMemo, useRef, useState } from 'react';
import type { HciotLanguage } from '../../../../config/hciotTopics';
import type {
  HciotImage,
  HciotKnowledgeFile,
  HciotTopicCategory,
} from '../../../../services/api/hciot';
import type { QaWorkspaceApiClient } from '../QaKnowledgeWorkspace';
import { categoryPrefix } from '../topicUtils';

export interface UseWorkspaceDataOptions {
  api: QaWorkspaceApiClient;
  language: HciotLanguage;
  onTopicsChanged?: () => Promise<void> | void;
  text: (zh: string, en: string) => string;
}

export function useWorkspaceData({
  api,
  language,
  onTopicsChanged,
  text,
}: UseWorkspaceDataOptions) {
  const statusTimerRef = useRef<number | null>(null);

  const [files, setFiles] = useState<HciotKnowledgeFile[]>([]);
  const [categories, setCategories] = useState<HciotTopicCategory[]>([]);
  const [images, setImages] = useState<HciotImage[]>([]);
  const [selectedFileName, setSelectedFileName] = useState<string | null>(null);
  const [selectedImageName, setSelectedImageName] = useState<string | null>(null);
  const [selectedMergedTopicId, setSelectedMergedTopicId] = useState<string | null>(null);
  const [loadingWorkspace, setLoadingWorkspace] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [topicRefreshKey, setTopicRefreshKey] = useState(0);

  const showStatus = (message: string) => {
    if (statusTimerRef.current !== null) {
      window.clearTimeout(statusTimerRef.current);
    }
    setStatusMessage(message);
    statusTimerRef.current = window.setTimeout(() => {
      setStatusMessage(null);
      statusTimerRef.current = null;
    }, 3200);
  };

  const selectedFile = useMemo(
    () => files.find((file) => file.name === selectedFileName) || null,
    [files, selectedFileName],
  );

  const selectedImage = useMemo(
    () => images.find((img) => img.image_id === selectedImageName) || null,
    [images, selectedImageName],
  );

  const unusedImageCount = useMemo(
    () => images.filter((image) => (image.reference_count ?? 0) === 0).length,
    [images],
  );

  const selectedMergedTopic = useMemo(() => {
    if (!selectedMergedTopicId) {
      return null;
    }
    const categoryId = categoryPrefix(selectedMergedTopicId);
    const category = categories.find((item) => item.id === categoryId);
    return category?.topics.find((item) => item.id === selectedMergedTopicId) ?? null;
  }, [categories, selectedMergedTopicId]);

  const selectedMergedLabel = selectedMergedTopic?.label ?? selectedMergedTopicId;

  const refreshWorkspace = async (preferredFileName?: string | null) => {
    setLoadingWorkspace(true);
    try {
      const [knowledgeResponse, topicsResponse, imagesResponse] = await Promise.all([
        api.listKnowledgeFiles(language),
        api.listTopicsAdmin(language),
        api.listImages(),
      ]);

      const nextFiles = knowledgeResponse.files || [];
      setFiles(nextFiles);
      setCategories(topicsResponse.categories || []);
      setImages(imagesResponse.images || []);
      setSelectedFileName((current) => {
        // Read latest selection via setter callbacks to avoid stale-closure:
        // completeUpload may have just set a merged-topic selection synchronously
        // before this refresh resolves.
        let hasOtherSelection = false;
        setSelectedImageName((img) => { hasOtherSelection = hasOtherSelection || !!img; return img; });
        setSelectedMergedTopicId((merged) => { hasOtherSelection = hasOtherSelection || !!merged; return merged; });
        if (hasOtherSelection) return null;
        const candidate = preferredFileName ?? current;
        if (candidate && nextFiles.some((file) => file.name === candidate)) {
          return candidate;
        }
        return null;
      });
    } catch (error) {
      console.error('Failed to load knowledge workspace:', error);
      showStatus(text('載入檔案管理失敗', 'Failed to load file workspace'));
    } finally {
      setLoadingWorkspace(false);
    }
  };

  const refreshWorkspaceAfterTopicChange = async (preferredFileName?: string | null) => {
    await refreshWorkspace(preferredFileName);
    await onTopicsChanged?.();
    setTopicRefreshKey((current) => current + 1);
  };

  const completeUpload = async (
    firstUploadedFileName: string | null,
    message: string,
    topicId?: string | null,
  ) => {
    if (topicId) {
      // Land on the topic's merged Q&A view instead of the freshly-created
      // single csv file, so users don't see the file-detail pane flash first.
      setSelectedFileName(null);
      setSelectedImageName(null);
      setSelectedMergedTopicId(topicId);
      await refreshWorkspaceAfterTopicChange(null);
    } else {
      await refreshWorkspaceAfterTopicChange(firstUploadedFileName);
    }
    showStatus(message);
  };

  return {
    files,
    setFiles,
    categories,
    setCategories,
    images,
    setImages,
    selectedFileName,
    setSelectedFileName,
    selectedImageName,
    setSelectedImageName,
    selectedMergedTopicId,
    setSelectedMergedTopicId,
    loadingWorkspace,
    statusMessage,
    showStatus,
    selectedFile,
    selectedImage,
    unusedImageCount,
    selectedMergedTopic,
    selectedMergedLabel,
    topicRefreshKey,
    refreshWorkspace,
    refreshWorkspaceAfterTopicChange,
    completeUpload,
    statusTimerRef,
  };
}
