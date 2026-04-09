import { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';

import type { HciotLanguage } from '../../config/hciotTopics';
import type { HciotKnowledgeFile, HciotTopicCategory } from '../../services/api/hciot';
import * as api from '../../services/api';
import ExplorerSidebar from './knowledgeWorkspace/explorer/ExplorerSidebar';
import FileDetailPane from './knowledgeWorkspace/detail/FileDetailPane';
import MergedCsvPane from './knowledgeWorkspace/detail/MergedCsvPane';
import UploadDialog from './knowledgeWorkspace/upload/UploadDialog';
import ImageDetailPane from './knowledgeWorkspace/detail/ImageDetailPane';
import { NEW_VALUE, buildLabels, buildCategoryOptions, buildTopicOptions, createEmptyDraft, draftFromFile, getErrorMessage, getDraftMetadataPayload, slugify, type FileMetadataDraft, type TopicLabels } from './knowledgeWorkspace/topicUtils';
import { buildExplorerTree, filterExplorerNodes, flattenExplorerNodes, getCurrentPathLabel, readExpandedKeys, writeExpandedKeys } from './knowledgeWorkspace/explorer/explorerTree';

interface HciotKnowledgeWorkspaceProps {
  active: boolean;
  language: HciotLanguage;
}

export default function HciotKnowledgeWorkspace({
  active,
  language,
}: HciotKnowledgeWorkspaceProps) {
  const emptyTopicDraft = (): Pick<FileMetadataDraft, 'topicId' | 'topicLabelZh' | 'topicLabelEn'> => ({
    topicId: '',
    topicLabelZh: '',
    topicLabelEn: '',
  });

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

  const deferredSearchQuery = useDeferredValue(searchQuery.trim().toLowerCase());

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

  const selectedMergedLabel = useMemo(() => {
    if (!selectedMergedTopicId) return null;
    const prefix = selectedMergedTopicId.split('/')[0];
    const cat = categories.find((c) => c.id === prefix);
    return cat?.topics.find((t) => t.id === selectedMergedTopicId)?.labels[language]
      ?? selectedMergedTopicId;
  }, [categories, language, selectedMergedTopicId]);

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
        api.listHciotTopicsAdmin(),
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
      showStatus(language === 'zh' ? '載入檔案管理失敗' : 'Failed to load file workspace');
    } finally {
      setLoadingWorkspace(false);
    }
  };

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
        setContentMessage(language === 'zh' ? '無法載入檔案內容' : 'Unable to load file content');
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
    return window.confirm(
      language === 'zh'
        ? '目前檔案有尚未儲存的變更，確定要切換嗎？'
        : 'You have unsaved changes. Switch anyway?',
    );
  };

  const handleSelectFile = (fileName: string) => {
    if (fileName === selectedFileName || !discardChanges()) return;
    ensureSelectedPathExpanded(fileName);
    setSelectedFileName(fileName);
    setSelectedImageName(null);
    setSelectedMergedTopicId(null);
  };

  const handleSelectImage = (fileName: string) => {
    if (!discardChanges()) return;
    setSelectedImageName(fileName);
    setSelectedFileName(null);
    setSelectedMergedTopicId(null);
  };

  const handleSelectMergedCsv = (topicId: string) => {
    if (!discardChanges()) return;
    setSelectedMergedTopicId(topicId);
    setSelectedFileName(null);
    setSelectedImageName(null);
  };

  const uploadFileWithTopic = async (
    file: File,
    topicId: string | null,
    labels: TopicLabels | null,
  ) => {
    if (!topicId) {
      return api.uploadHciotKnowledgeFile(language, file);
    }
    const catId = topicId.split('/')[0];
    const topicSlug = topicId.includes('/') ? topicId.split('/').slice(1).join('/') : '';
    return api.uploadHciotKnowledgeFileWithTopic({
      language,
      file,
      categoryId: catId || undefined,
      topicId: topicSlug || undefined,
      categoryLabelZh: labels?.categoryLabelZh || undefined,
      categoryLabelEn: labels?.categoryLabelEn || undefined,
      topicLabelZh: labels?.topicLabelZh || undefined,
      topicLabelEn: labels?.topicLabelEn || undefined,
    });
  };

  const handleUploadFile = async (
    file: File,
    topicId: string | null,
    labels: TopicLabels | null,
  ) => {
    return uploadFileWithTopic(file, topicId, labels);
  };

  const handleUploadComplete = async (firstUploadedFileName: string | null, count: number) => {
    await refreshWorkspace(firstUploadedFileName);
    setQaDialogOpen(false);
    showStatus(
      language === 'zh'
        ? `已上傳 ${count} 個檔案`
        : `Uploaded ${count} file(s)`,
    );
  };

  const handleQASubmit = async (
    file: File,
    topicId: string,
    labels: TopicLabels,
  ) => {
    setUploading(true);
    try {
      const response = await uploadFileWithTopic(file, topicId, labels);
      await handleUploadComplete(response.name, response.uploaded_count ?? 1);
    } catch (error) {
      console.error('Failed to upload HCIoT files:', error);
      alert(getErrorMessage(error));
    } finally {
      setUploading(false);
    }
  };

  const handleDeleteFile = async () => {
    if (!selectedFile) {
      return;
    }

    const confirmed = window.confirm(
      language === 'zh'
        ? `確定要刪除 ${selectedFile.display_name || selectedFile.name}？`
        : `Delete ${selectedFile.display_name || selectedFile.name}?`,
    );
    if (!confirmed) {
      return;
    }

    setDeleting(true);
    try {
      await api.deleteHciotKnowledgeFile(selectedFile.name, language);
      await refreshWorkspace();
      showStatus(language === 'zh' ? '檔案已刪除' : 'File deleted');
    } catch (error) {
      console.error('Failed to delete HCIoT file:', error);
      alert(getErrorMessage(error));
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteImage = async () => {
    if (!selectedImage) return;
    const referenceCount = selectedImage.reference_count ?? 0;
    let confirmMessage = language === 'zh'
      ? `確定要刪除圖片 ${selectedImage.image_id}？`
      : `Delete image ${selectedImage.image_id}?`;
    if (referenceCount > 0) {
      confirmMessage = language === 'zh'
        ? `圖片 ${selectedImage.image_id} 目前被 ${referenceCount} 題引用，刪除後相關回答將無法顯示圖片。確定要刪除嗎？`
        : `Image ${selectedImage.image_id} is still referenced by ${referenceCount} item(s). Delete it anyway?`;
    }
    const confirmed = window.confirm(confirmMessage);
    if (!confirmed) return;
    setDeleting(true);
    try {
      await api.deleteHciotImage(selectedImage.image_id);
      await refreshWorkspace();
      setSelectedImageName(null);
      showStatus(language === 'zh' ? '圖片已刪除' : 'Image deleted');
    } catch (error: any) {
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

    const confirmed = window.confirm(
      language === 'zh'
        ? `確定要刪除 ${unusedImageCount} 張未被任何題目引用的圖片？`
        : `Delete ${unusedImageCount} unused image(s)?`,
    );
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
      showStatus(
        language === 'zh'
          ? `已刪除 ${response.deleted_count} 張未引用圖片`
          : `Deleted ${response.deleted_count} unused image(s)`,
      );
    } catch (error) {
      console.error('Failed to clean unused HCIoT images:', error);
      alert(getErrorMessage(error));
    } finally {
      setCleaningUnusedImages(false);
    }
  };

  const handleUploadImageComplete = async (count: number) => {
    await refreshWorkspace();
    setQaDialogOpen(false);
    showStatus(language === 'zh' ? `已上傳 ${count} 張圖片` : `Uploaded ${count} image(s)`);
  };

  const currentCategory = useMemo(() => {
    if (!draft.categoryId || draft.categoryId === NEW_VALUE) {
      return null;
    }
    return categories.find((item) => item.id === draft.categoryId) || null;
  }, [categories, draft.categoryId]);

  const topicOptions = useMemo(
    () => buildTopicOptions(currentCategory, draft, language),
    [currentCategory, draft, language],
  );

  const categoryOptions = useMemo(
    () => buildCategoryOptions(categories, draft, language),
    [categories, draft, language],
  );

  const handleCategoryChange = (value: string) => {
    if (!value) {
      setDraft(createEmptyDraft());
      return;
    }

    if (value === NEW_VALUE) {
      patchDraft({
        categoryId: NEW_VALUE,
        categoryLabelZh: '',
        categoryLabelEn: '',
        ...emptyTopicDraft(),
      });
      return;
    }

    const category = categoryOptions.find((item) => item.id === value);
    setDraft({
      categoryId: value,
      categoryLabelZh: category?.labels.zh || '',
      categoryLabelEn: category?.labels.en || '',
      ...emptyTopicDraft(),
    });
  };

  const handleTopicChange = (value: string) => {
    if (!value) {
      setDraft((previous) => ({
        ...previous,
        ...emptyTopicDraft(),
      }));
      return;
    }

    if (value === NEW_VALUE) {
      setDraft((previous) => ({
        ...previous,
        topicId: NEW_VALUE,
        topicLabelZh: '',
        topicLabelEn: '',
      }));
      return;
    }

    const topic = topicOptions.find((item) => item.id === value);
    patchDraft({
      topicId: value,
      topicLabelZh: topic?.labels.zh || '',
      topicLabelEn: topic?.labels.en || '',
    });
  };

  const handleSave = async () => {
    if (!selectedFile) {
      return;
    }

    setSaving(true);
    try {
      let nextDraft = { ...draft };

      if (nextDraft.categoryId === NEW_VALUE) {
        const labels = buildLabels(nextDraft.categoryLabelZh, nextDraft.categoryLabelEn);
        if (!labels) {
          throw new Error(language === 'zh' ? '請輸入新科別名稱' : 'Please enter a category name');
        }
        const createdCategoryId = slugify(labels.en || labels.zh);
        if (!createdCategoryId) {
          throw new Error(language === 'zh' ? '無法建立科別 ID' : 'Unable to create category id');
        }
        nextDraft = {
          ...nextDraft,
          categoryId: createdCategoryId,
          categoryLabelZh: labels.zh,
          categoryLabelEn: labels.en,
        };
      }

      if (!nextDraft.categoryId) {
        nextDraft = {
          ...nextDraft,
          ...emptyTopicDraft(),
        };
      } else if (nextDraft.topicId === NEW_VALUE) {
        const labels = buildLabels(nextDraft.topicLabelZh, nextDraft.topicLabelEn);
        if (!labels) {
          throw new Error(language === 'zh' ? '請輸入新主題名稱' : 'Please enter a topic name');
        }
        const createdTopicSlug = slugify(labels.en || labels.zh);
        if (!createdTopicSlug) {
          throw new Error(language === 'zh' ? '無法建立主題 ID' : 'Unable to create topic id');
        }

        const fullTopicId = `${nextDraft.categoryId}/${createdTopicSlug}`;
        const categoryLabels = buildLabels(nextDraft.categoryLabelZh, nextDraft.categoryLabelEn)
          || { zh: nextDraft.categoryId, en: nextDraft.categoryId };
        await api.createHciotTopic(fullTopicId, labels, categoryLabels);
        const topicData = await api.listHciotTopicsAdmin();
        setCategories(topicData.categories || []);
        nextDraft = {
          ...nextDraft,
          topicId: fullTopicId,
          topicLabelZh: labels.zh,
          topicLabelEn: labels.en,
        };
      }

      if (metadataDirty || draft.categoryId === NEW_VALUE || draft.topicId === NEW_VALUE) {
        const updatedMetadata = await api.updateHciotKnowledgeFileMetadata(
          selectedFile.name,
          getDraftMetadataPayload(nextDraft),
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
      await refreshWorkspace(selectedFile.name);
      showStatus(language === 'zh' ? '變更已儲存' : 'Changes saved');
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
        language={language}
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
      />

      <UploadDialog
        open={qaDialogOpen}
        language={language}
        categories={categories}
        availableImages={images}
        uploading={uploading}
        onClose={() => setQaDialogOpen(false)}
        onUploadFile={handleUploadFile}
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
          onRefreshWorkspace={() => refreshWorkspace()}
          onUploadImage={api.uploadHciotImage}
          onDeleteImage={api.deleteHciotImage}
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
