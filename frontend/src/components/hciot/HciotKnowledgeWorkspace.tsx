import { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';

import type { HciotLanguage } from '../../config/hciotTopics';
import type { HciotKnowledgeFile, HciotTopicCategory } from '../../services/api/hciot';
import * as api from '../../services/api';
import ExplorerSidebar from './knowledgeWorkspace/explorer/ExplorerSidebar';
import FileDetailPane from './knowledgeWorkspace/detail/FileDetailPane';
import MergedCsvPane from './knowledgeWorkspace/detail/MergedCsvPane';
import UploadDialog from './knowledgeWorkspace/upload/UploadDialog';
import ImageDetailPane from './knowledgeWorkspace/detail/ImageDetailPane';
import { NEW_VALUE, buildCategoryOptions, buildTopicOptions, categoryPrefix, createEmptyDraft, draftFromFile, getErrorMessage, getMetadataPayload, normalizeLabel, slugify, type FileMetadataDraft, type TopicLabels } from './knowledgeWorkspace/topicUtils';
import { useEscapeKey } from '../../hooks/useEscapeKey';
import { buildExplorerTree, filterExplorerNodes, flattenExplorerNodes, getCurrentPathLabel, readExpandedKeys, writeExpandedKeys } from './knowledgeWorkspace/explorer/explorerTree';
import reindexRag from '../../services/api/general';

interface HciotKnowledgeWorkspaceProps {
  active: boolean;
  language: HciotLanguage;
  onTopicsChanged?: () => Promise<void> | void;
}

function createEmptyTopicDraft(): Pick<FileMetadataDraft, 'topicId' | 'topicLabel'> {
  return {
    topicId: '',
    topicLabel: '',
  };
}

function getLocalizedText(_language: HciotLanguage, zh: string, _en: string): string {
  return zh;
}

interface ParsedExplorerKey {
  kind: string;
  id: string;
}

function parseExplorerKey(key: string): ParsedExplorerKey {
  const separatorIndex = key.indexOf(':');
  return separatorIndex === -1
    ? { kind: key, id: '' }
    : { kind: key.slice(0, separatorIndex), id: key.slice(separatorIndex + 1) };
}

function splitTopicId(topicId: string): { categoryId: string; topicSlug: string } {
  const [categoryId = '', ...topicParts] = topicId.split('/');
  return { categoryId, topicSlug: topicParts.join('/') };
}

function moveItem<T>(items: T[], from: number, to: number): T[] | null {
  if (from === -1 || to === -1) {
    return null;
  }

  const nextItems = [...items];
  const [moved] = nextItems.splice(from, 1);
  nextItems.splice(to, 0, moved);
  return nextItems;
}

export default function HciotKnowledgeWorkspace({
  active,
  language,
  onTopicsChanged,
}: HciotKnowledgeWorkspaceProps) {
  const statusTimerRef = useRef<number | null>(null);
  const suppressHoverRef = useRef(false);

  const [files, setFiles] = useState<HciotKnowledgeFile[]>([]);
  const [categories, setCategories] = useState<HciotTopicCategory[]>([]);
  const [images, setImages] = useState<api.HciotImage[]>([]);
  const [selectedFileName, setSelectedFileName] = useState<string | null>(null);
  const [selectedImageName, setSelectedImageName] = useState<string | null>(null);
  const [selectedMergedTopicId, setSelectedMergedTopicId] = useState<string | null>(null);
  const [expandedKeys, setExpandedKeys] = useState<string[]>(() => readExpandedKeys(language));
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarHoverExpanded, setSidebarHoverExpanded] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [loadingWorkspace, setLoadingWorkspace] = useState(false);
  const [loadingContent, setLoadingContent] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [cleaningUnusedImages, setCleaningUnusedImages] = useState(false);
  const [editorText, setEditorText] = useState('');
  const [originalText, setOriginalText] = useState('');
  const [fileEditable, setFileEditable] = useState(false);
  const [contentMessage, setContentMessage] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [draft, setDraft] = useState<FileMetadataDraft>(createEmptyDraft());
  const [qaDialogOpen, setQaDialogOpen] = useState(false);
  const [reindexing, setReindexing] = useState(false);
  const [renamingKey, setRenamingKey] = useState<string | null>(null);
  const [renaming, setRenaming] = useState(false);

  const deferredSearchQuery = useDeferredValue(searchQuery.trim().toLowerCase());
  const text = (zh: string, en: string) => getLocalizedText(language, zh, en);

  const patchDraft = (changes: Partial<FileMetadataDraft>) => {
    setDraft((previous) => ({ ...previous, ...changes }));
  };

  useEffect(() => {
    setExpandedKeys(readExpandedKeys(language));
  }, [language]);

  useEffect(() => {
    writeExpandedKeys(language, expandedKeys);
  }, [expandedKeys, language]);

  useEffect(() => () => {
    if (statusTimerRef.current !== null) {
      window.clearTimeout(statusTimerRef.current);
    }
  }, []);

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

  const metadataDirty = useMemo(() => {
    if (!selectedFile) {
      return false;
    }
    if (draft.categoryId === NEW_VALUE || draft.topicId === NEW_VALUE) {
      return true;
    }

    const cleanDraft = draftFromFile(selectedFile, categories);
    return JSON.stringify(cleanDraft) !== JSON.stringify(draft);
  }, [categories, draft, selectedFile]);

  const contentDirty = fileEditable && editorText !== originalText;
  const hasUnsavedChanges = metadataDirty || contentDirty;

  const { roots, filePathKeys } = useMemo(
    () => buildExplorerTree(files, categories, language, images),
    [categories, files, language, images],
  );

  const filteredRoots = useMemo(
    () => filterExplorerNodes(roots, deferredSearchQuery),
    [deferredSearchQuery, roots],
  );

  const visibleExpandedKeys = useMemo(() => new Set(expandedKeys), [expandedKeys]);

  const visibleRows = useMemo(
    () => flattenExplorerNodes(filteredRoots, visibleExpandedKeys, deferredSearchQuery),
    [deferredSearchQuery, filteredRoots, visibleExpandedKeys],
  );

  const refreshWorkspace = async (preferredFileName?: string | null) => {
    setLoadingWorkspace(true);
    try {
      const [knowledgeResponse, topicsResponse, imagesResponse] = await Promise.all([
        api.listHciotKnowledgeFiles(language),
        api.listHciotTopicsAdmin(language),
        api.listHciotImages(),
      ]);

      const nextFiles = knowledgeResponse.files || [];
      setFiles(nextFiles);
      setCategories(topicsResponse.categories || []);
      setImages(imagesResponse.images || []);
      setSelectedFileName((current) => {
        if (selectedImageName || selectedMergedTopicId) return null;
        const candidate = preferredFileName ?? current;
        if (candidate && nextFiles.some((file) => file.name === candidate)) {
          return candidate;
        }
        return null;
      });
    } catch (error) {
      console.error('Failed to load HCIoT knowledge workspace:', error);
      showStatus(text('載入檔案管理失敗', 'Failed to load file workspace'));
    } finally {
      setLoadingWorkspace(false);
    }
  };

  const refreshWorkspaceAfterTopicChange = async (preferredFileName?: string | null) => {
    await refreshWorkspace(preferredFileName);
    await onTopicsChanged?.();
  };

  const handleReindex = async () => {
    if (reindexing) return;
    if (!window.confirm(text(
      '確定要重新索引嗎？這將會暫停服務約 1 分鐘。',
      'Are you sure you want to reindex? This will pause service for about 1 minute.',
    ))) {
      return;
    }

    setReindexing(true);
    try {
      await reindexRag('hciot');
      showStatus(text('重新索引已開始', 'Reindexing started'));
    } catch (error) {
      console.error('Failed to reindex HCIoT RAG:', error);
      alert(getErrorMessage(error));
    } finally {
      // Reindexing is background task, we just unlock the button after a while
      // or let it stay disabled for a bit.
      window.setTimeout(() => setReindexing(false), 5000);
    }
  };

  // Selections (file / image / merged-csv topic) belong to one language's
  // dataset. When the language switches, the previously selected item may not
  // exist in the new dataset — clear all selections so no detail pane is left
  // pointing at a stale id.
  useEffect(() => {
    setSelectedFileName(null);
    setSelectedImageName(null);
    setSelectedMergedTopicId(null);
  }, [language]);

  useEffect(() => {
    if (!active) {
      return;
    }
    void refreshWorkspace();
  }, [active, language]);

  useEffect(() => {
    if (!selectedFileName) {
      setDraft(createEmptyDraft());
      return;
    }

    if (selectedFile) {
      setDraft(draftFromFile(selectedFile, categories));
    }
  }, [categories, selectedFile, selectedFileName]);

  useEffect(() => {
    if (!selectedFileName) {
      setEditorText('');
      setOriginalText('');
      setFileEditable(false);
      setContentMessage(null);
      return;
    }

    let cancelled = false;
    setLoadingContent(true);
    api.getHciotKnowledgeFileContent(selectedFileName, language)
      .then((response) => {
        if (cancelled) {
          return;
        }
        const nextContent = response.content || '';
        setOriginalText(nextContent);
        setEditorText(nextContent);
        setFileEditable(Boolean(response.editable));
        setContentMessage(response.message || null);
      })
      .catch((error) => {
        console.error('Failed to load HCIoT file content:', error);
        if (cancelled) {
          return;
        }
        setOriginalText('');
        setEditorText('');
        setFileEditable(false);
        setContentMessage(text('無法載入檔案內容', 'Unable to load file content'));
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingContent(false);
        }
      });


    return () => {
      cancelled = true;
    };
  }, [language, selectedFileName]);

  const toggleExpanded = (key: string) => {
    setExpandedKeys((previous) => {
      if (previous.includes(key)) {
        return previous.filter((item) => item !== key);
      }
      return [...previous, key];
    });
  };

  const ensureSelectedPathExpanded = (fileName: string) => {
    const ancestorKeys = filePathKeys.get(fileName) || [];
    if (!ancestorKeys.length) {
      return;
    }

    setExpandedKeys((previous) => {
      const nextKeys = new Set(previous);
      ancestorKeys.forEach((key) => nextKeys.add(key));
      return [...nextKeys];
    });
  };

  const discardChanges = () => {
    if (!hasUnsavedChanges) return true;
    return window.confirm(text(
      '目前檔案有尚未儲存的變更，確定要切換嗎？',
      'You have unsaved changes. Switch anyway?',
    ));
  };

  const selectWorkspaceItem = ({
    fileName = null,
    imageName = null,
    mergedTopicId = null,
  }: {
    fileName?: string | null;
    imageName?: string | null;
    mergedTopicId?: string | null;
  }) => {
    setSelectedFileName(fileName);
    setSelectedImageName(imageName);
    setSelectedMergedTopicId(mergedTopicId);
  };

  const hasSelection = !!(selectedFileName || selectedImageName || selectedMergedTopicId);
  useEscapeKey(() => { if (discardChanges()) selectWorkspaceItem({}); }, hasSelection);

  const handleSelectFile = (fileName: string) => {
    if (fileName === selectedFileName || !discardChanges()) return;
    ensureSelectedPathExpanded(fileName);
    selectWorkspaceItem({ fileName });
  };

  const handleSelectImage = (fileName: string) => {
    if (!discardChanges()) return;
    selectWorkspaceItem({ imageName: fileName });
  };

  const handleSelectMergedCsv = (topicId: string) => {
    if (!discardChanges()) return;
    selectWorkspaceItem({ mergedTopicId: topicId });
  };

  const uploadFileWithTopic = async (
    file: File,
    topicId: string | null,
    labels: TopicLabels | null,
    skipTopic?: boolean,
    hiddenQuestions?: string[],
  ) => {
    if (skipTopic) {
      return api.uploadHciotKnowledgeFileWithTopic({
        language,
        file,
        skipTopic: true,
      });
    }
    if (!topicId) {
      return api.uploadHciotKnowledgeFile(language, file);
    }
    const { categoryId, topicSlug } = splitTopicId(topicId);
    return api.uploadHciotKnowledgeFileWithTopic({
      language,
      file,
      categoryId: categoryId || undefined,
      topicId: topicSlug || undefined,
      categoryLabel: labels?.categoryLabel || undefined,
      topicLabel: labels?.topicLabel || undefined,
      hiddenQuestions,
    });
  };

  const completeUpload = async (firstUploadedFileName: string | null, message: string) => {
    await refreshWorkspaceAfterTopicChange(firstUploadedFileName);
    setQaDialogOpen(false);
    showStatus(message);
  };

  const handleUploadComplete = async (firstUploadedFileName: string | null, count: number) => {
    await completeUpload(firstUploadedFileName, text(
      `已上傳 ${count} 個檔案`,
      `Uploaded ${count} file(s)`,
    ));
  };

  const handleQASubmit = async (
    file: File,
    topicId: string,
    labels: TopicLabels,
    hiddenQuestions: string[],
  ): Promise<{ name: string; uploaded_count: number }> => {
    setUploading(true);
    try {
      // hidden_questions is written atomically with the extracted questions in
      // a single backend call — QaUploadTab then calls onUploadComplete itself.
      const response = await uploadFileWithTopic(file, topicId, labels, false, hiddenQuestions);
      return { name: response.name, uploaded_count: response.uploaded_count ?? 1 };
    } finally {
      setUploading(false);
    }
  };

  const handleDeleteFile = async () => {
    if (!selectedFile) {
      return;
    }

    const confirmed = window.confirm(text(
      `確定要刪除 ${selectedFile.display_name || selectedFile.name}？`,
      `Delete ${selectedFile.display_name || selectedFile.name}?`,
    ));
    if (!confirmed) {
      return;
    }

    setDeleting(true);
    try {
      await api.deleteHciotKnowledgeFile(selectedFile.name, language);
      await refreshWorkspaceAfterTopicChange();
      showStatus(text('檔案已刪除', 'File deleted'));
    } catch (error) {
      console.error('Failed to delete HCIoT file:', error);
      alert(getErrorMessage(error));
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteTopic = async (topicId: string, topicLabel: string) => {
    const targets = files.filter((file) => file.topic_id === topicId);
    if (!targets.length) return;
    const confirmed = window.confirm(text(
      `確定要刪除主題「${topicLabel}」？無法復原。`,
      `Delete topic "${topicLabel}"? This cannot be undone.`,
    ));
    if (!confirmed) return;

    setDeleting(true);
    try {
      const results = await Promise.allSettled(
        targets.map((file) => api.deleteHciotKnowledgeFile(file.name, language)),
      );
      const failed = results.filter((result) => result.status === 'rejected').length;
      if (selectedMergedTopicId === topicId) {
        setSelectedMergedTopicId(null);
      }
      const targetNames = new Set(targets.map((file) => file.name));
      if (selectedFileName && targetNames.has(selectedFileName)) {
        setSelectedFileName(null);
      }
      await refreshWorkspaceAfterTopicChange();
      if (failed) {
        alert(text(
          `主題「${topicLabel}」刪除完成，但有 ${failed} 個檔案失敗`,
          `Topic "${topicLabel}" deleted with ${failed} file failures`,
        ));
      } else {
        showStatus(text(`主題「${topicLabel}」已刪除`, `Topic "${topicLabel}" deleted`));
      }
    } catch (error) {
      console.error('Failed to delete HCIoT topic:', error);
      alert(getErrorMessage(error));
    } finally {
      setDeleting(false);
    }
  };

  const handleStartRename = (key: string) => {
    if (!discardChanges()) return;
    setRenamingKey(key);
  };

  const handleCancelRename = () => {
    setRenamingKey(null);
  };

  const handleCommitRename = async (key: string, nextLabel: string) => {
    const label = nextLabel.trim();
    if (!label) {
      setRenamingKey(null);
      return;
    }

    const { kind, id: targetId } = parseExplorerKey(key);
    if (!targetId) {
      setRenamingKey(null);
      return;
    }

    const isCategoryRename = kind === 'category';
    const topicIds =
      isCategoryRename
        ? (categories.find((cat) => cat.id === targetId)?.topics ?? []).map((topic) => topic.id)
        : [targetId];

    if (!topicIds.length) {
      setRenamingKey(null);
      return;
    }

    setRenaming(true);
    try {
      const payload = isCategoryRename ? { category_labels: label } : { labels: label };
      const results = await Promise.allSettled(
        topicIds.map((topicId) => api.updateHciotTopic(topicId, payload, language)),
      );
      const failed = results.filter((result) => result.status === 'rejected').length;
      setRenamingKey(null);
      await refreshWorkspaceAfterTopicChange(selectedFileName);
      if (failed) {
        alert(text(
          `改名完成，但有 ${failed} 個項目失敗`,
          `Rename completed with ${failed} failure(s)`,
        ));
      } else {
        showStatus(text('名稱已更新', 'Name updated'));
      }
    } catch (error) {
      console.error('Failed to rename HCIoT category/topic:', error);
      alert(getErrorMessage(error));
    } finally {
      setRenaming(false);
    }
  };

  const handleReorder = async (activeKey: string, overKey: string) => {
    const active = parseExplorerKey(activeKey);
    const over = parseExplorerKey(overKey);
    if (active.kind !== over.kind || !active.id || !over.id) {
      return;
    }

    let orderedCategories: HciotTopicCategory[] | null = null;

    if (active.kind === 'category') {
      orderedCategories = moveItem(
        categories,
        categories.findIndex((category) => category.id === active.id),
        categories.findIndex((category) => category.id === over.id),
      );
    } else if (active.kind === 'topic') {
      const activeCategoryId = categoryPrefix(active.id);
      if (activeCategoryId !== categoryPrefix(over.id)) {
        return;
      }

      const categoryIndex = categories.findIndex((category) => category.id === activeCategoryId);
      if (categoryIndex === -1) {
        return;
      }

      const category = categories[categoryIndex];
      const topics = moveItem(
        category.topics,
        category.topics.findIndex((topic) => topic.id === active.id),
        category.topics.findIndex((topic) => topic.id === over.id),
      );
      if (!topics) return;
      orderedCategories = [...categories];
      orderedCategories[categoryIndex] = { ...category, topics };
    }

    if (!orderedCategories) {
      return;
    }

    const topicIds = orderedCategories.flatMap((cat) => cat.topics.map((topic) => topic.id));
    if (!topicIds.length) return;

    try {
      await api.reorderHciotTopics(topicIds, language);
      await refreshWorkspaceAfterTopicChange(selectedFileName);
      showStatus(text('順序已更新', 'Order updated'));
    } catch (error) {
      console.error('Failed to reorder HCIoT topics:', error);
      alert(getErrorMessage(error));
    }
  };

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
      await api.deleteHciotImage(selectedImage.image_id);
      await refreshWorkspace();
      setSelectedImageName(null);
      showStatus(text('圖片已刪除', 'Image deleted'));
    } catch (error) {
      console.error('Failed to delete HCIoT image:', error);
      alert(getErrorMessage(error));
    } finally {
      setDeleting(false);
    }
  };

  const handleCleanupUnusedImages = async () => {
    if (unusedImageCount === 0) {
      return;
    }

    const confirmed = window.confirm(text(
      `確定要刪除 ${unusedImageCount} 張未被任何題目引用的圖片？`,
      `Delete ${unusedImageCount} unused image(s)?`,
    ));
    if (!confirmed) {
      return;
    }

    setCleaningUnusedImages(true);
    try {
      const response = await api.deleteUnusedHciotImages();
      await refreshWorkspace();
      if (selectedImageName && response.deleted_image_ids.includes(selectedImageName)) {
        setSelectedImageName(null);
      }
      showStatus(text(
        `已刪除 ${response.deleted_count} 張未引用圖片`,
        `Deleted ${response.deleted_count} unused image(s)`,
      ));
    } catch (error) {
      console.error('Failed to clean unused HCIoT images:', error);
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

  const currentCategory = useMemo(() => {
    if (!draft.categoryId || draft.categoryId === NEW_VALUE) {
      return null;
    }
    return categories.find((item) => item.id === draft.categoryId) || null;
  }, [categories, draft.categoryId]);

  const topicOptions = useMemo(
    () => buildTopicOptions(currentCategory, draft),
    [currentCategory, draft],
  );

  const categoryOptions = useMemo(
    () => buildCategoryOptions(categories, draft),
    [categories, draft],
  );

  const handleCategoryChange = (value: string) => {
    if (!value) {
      setDraft(createEmptyDraft());
      return;
    }

    if (value === NEW_VALUE) {
      patchDraft({
        categoryId: NEW_VALUE,
        categoryLabel: '',
        ...createEmptyTopicDraft(),
      });
      return;
    }

    const category = categoryOptions.find((item) => item.id === value);
    setDraft({
      categoryId: value,
      categoryLabel: category?.label || '',
      ...createEmptyTopicDraft(),
    });
  };

  const handleTopicChange = (value: string) => {
    if (!value) {
      setDraft((previous) => ({
        ...previous,
        ...createEmptyTopicDraft(),
      }));
      return;
    }

    if (value === NEW_VALUE) {
      setDraft((previous) => ({
        ...previous,
        topicId: NEW_VALUE,
        topicLabel: '',
      }));
      return;
    }

    const topic = topicOptions.find((item) => item.id === value);
    patchDraft({
      topicId: value,
      topicLabel: topic?.label || '',
    });
  };

  const resolveDraftBeforeSave = async (currentDraft: FileMetadataDraft): Promise<FileMetadataDraft> => {
    let nextDraft = { ...currentDraft };

    if (nextDraft.categoryId === NEW_VALUE) {
      const categoryLabel = normalizeLabel(nextDraft.categoryLabel);
      if (!categoryLabel) {
        throw new Error(text('請輸入新科別的名稱', 'Please enter a category label'));
      }
      const createdCategoryId = slugify(categoryLabel);
      if (!createdCategoryId) {
        throw new Error(text('無法建立科別 ID', 'Unable to create category id'));
      }
      nextDraft = {
        ...nextDraft,
        categoryId: createdCategoryId,
        categoryLabel,
      };
    }

    if (!nextDraft.categoryId) {
      return {
        ...nextDraft,
        ...createEmptyTopicDraft(),
      };
    }

    if (nextDraft.topicId !== NEW_VALUE) {
      return nextDraft;
    }

    const topicLabel = normalizeLabel(nextDraft.topicLabel);
    if (!topicLabel) {
      throw new Error(text('請輸入新主題的名稱', 'Please enter a topic label'));
    }
    const createdTopicSlug = slugify(topicLabel);
    if (!createdTopicSlug) {
      throw new Error(text('無法建立主題 ID', 'Unable to create topic id'));
    }

    const fullTopicId = `${nextDraft.categoryId}/${createdTopicSlug}`;
    const categoryLabel = normalizeLabel(nextDraft.categoryLabel);
    if (!categoryLabel) {
      throw new Error(text('請輸入新科別的名稱', 'Please enter a category label'));
    }
    await api.createHciotTopic(fullTopicId, topicLabel, categoryLabel, undefined, language);
    const topicData = await api.listHciotTopicsAdmin(language);
    setCategories(topicData.categories || []);

    return {
      ...nextDraft,
      topicId: fullTopicId,
      topicLabel,
    };
  };

  const handleSave = async () => {
    if (!selectedFile) {
      return;
    }

    setSaving(true);
    try {
      const nextDraft = await resolveDraftBeforeSave(draft);

      if (metadataDirty || draft.categoryId === NEW_VALUE || draft.topicId === NEW_VALUE) {
        const updatedMetadata = await api.updateHciotKnowledgeFileMetadata(
          selectedFile.name,
          getMetadataPayload(nextDraft),
          language,
        );
        setFiles((previous) => previous.map((file) => (
          file.name === selectedFile.name
            ? { ...file, ...updatedMetadata }
            : file
        )));
      }

      if (contentDirty) {
        await api.updateHciotKnowledgeFileContent(selectedFile.name, editorText, language);
        setOriginalText(editorText);
      }

      setDraft(nextDraft);
      await refreshWorkspaceAfterTopicChange(selectedFile.name);
      showStatus(text('變更已儲存', 'Changes saved'));
    } catch (error) {
      console.error('Failed to save HCIoT file changes:', error);
      alert(getErrorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  const currentPathLabel = useMemo(
    () => getCurrentPathLabel(selectedFile, language),
    [language, selectedFile],
  );

  const sidebarExpanded = !sidebarCollapsed || sidebarHoverExpanded;

  const handleSidebarMouseEnter = () => {
    if (sidebarCollapsed && !suppressHoverRef.current) {
      setSidebarHoverExpanded(true);
    }
  };

  const handleSidebarMouseLeave = () => {
    if (sidebarCollapsed) {
      setSidebarHoverExpanded(false);
    }
  };

  const handleToggleSidebar = () => {
    const willCollapse = !sidebarCollapsed;
    setSidebarCollapsed(willCollapse);
    setSidebarHoverExpanded(false);

    if (willCollapse) {
      suppressHoverRef.current = true;
      window.setTimeout(() => {
        suppressHoverRef.current = false;
      }, 300);
    }
  };

  return (
    <section
      className={`hciot-files-workspace${active ? ' is-active' : ''}${sidebarExpanded ? ' is-sidebar-expanded' : ''}`}
    >
      <ExplorerSidebar
        sidebarCollapsed={sidebarCollapsed}
        loadingWorkspace={loadingWorkspace}
        searchQuery={searchQuery}
        deferredSearchQuery={deferredSearchQuery}
        selectedFileName={selectedFileName}
        selectedImageName={selectedImageName}
        visibleRows={visibleRows}
        visibleExpandedKeys={visibleExpandedKeys}
        onMouseEnter={handleSidebarMouseEnter}
        onMouseLeave={handleSidebarMouseLeave}
        onToggleSidebar={handleToggleSidebar}
        onSearchChange={setSearchQuery}
        onToggleExpanded={toggleExpanded}
        selectedMergedTopicId={selectedMergedTopicId}
        onSelectFile={handleSelectFile}
        onSelectImage={handleSelectImage}
        onSelectMergedCsv={handleSelectMergedCsv}
        onOpenUploadDialog={() => setQaDialogOpen(true)}
        onDeleteTopic={handleDeleteTopic}
        onReindex={handleReindex}
        reindexing={reindexing}
        renamingKey={renamingKey}
        renaming={renaming}
        onStartRename={handleStartRename}
        onCommitRename={handleCommitRename}
        onCancelRename={handleCancelRename}
        onReorder={handleReorder}
      />

      <UploadDialog
        open={qaDialogOpen}
        language={language}
        categories={categories}
        availableImages={images}
        uploading={uploading}
        onClose={() => setQaDialogOpen(false)}
        onUploadFile={uploadFileWithTopic}
        onUploadComplete={handleUploadComplete}
        onSubmitQA={handleQASubmit}
        onUploadImage={api.uploadHciotImage}
        onDeleteImage={api.deleteHciotImage}
        onUploadImageComplete={handleUploadImageComplete}
      />

      {selectedImageName ? (
        <ImageDetailPane
          language={language}
          selectedImage={selectedImage}
          deleting={deleting}
          cleaningUnused={cleaningUnusedImages}
          unusedImageCount={unusedImageCount}
          onDelete={() => void handleDeleteImage()}
          onCleanupUnused={() => void handleCleanupUnusedImages()}
        />
      ) : selectedMergedTopicId ? (
        <MergedCsvPane
          topicId={selectedMergedTopicId}
          topicLabel={selectedMergedLabel}
          language={language}
          availableImages={images}
          statusMessage={statusMessage}
          hiddenQuestions={selectedMergedTopic?.hidden_questions}
          onRefreshWorkspace={() => refreshWorkspaceAfterTopicChange()}
          onUploadImage={api.uploadHciotImage}
          onDeleteImage={api.deleteHciotImage}
          onDeleteTopic={handleDeleteTopic}
        />
      ) : (
        <FileDetailPane
          language={language}
          state={{
            selectedFile,
            currentPathLabel,
            statusMessage,
            deleting,
            saving,
            uploading,
            hasUnsavedChanges,
            draft,
            fileEditable,
            loadingContent,
            contentMessage,
            editorText,
          }}
          actions={{
            onDownload: () => {
              if (selectedFile) api.downloadHciotKnowledgeFile(selectedFile.name, language);
            },
            onDelete: () => { void handleDeleteFile(); },
            onSave: () => { void handleSave(); },
            onCategoryChange: handleCategoryChange,
            onTopicChange: handleTopicChange,
            onDraftChange: patchDraft,
            onEditorTextChange: setEditorText,
          }}
          categoryOptions={categoryOptions}
          topicOptions={topicOptions}
        />
      )}
    </section>
  );
}
