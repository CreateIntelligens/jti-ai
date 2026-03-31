import { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';

import type { HciotLanguage } from '../../config/hciotTopics';
import type { HciotKnowledgeFile, HciotTopicCategory } from '../../services/api/hciot';
import * as api from '../../services/api';
import ExplorerSidebar from './knowledgeWorkspace/ExplorerSidebar';
import FileDetailPane from './knowledgeWorkspace/FileDetailPane';
import UploadDialog from './knowledgeWorkspace/UploadDialog';
import {
  NEW_VALUE,
  buildExplorerTree,
  buildLabels,
  buildCategoryOptions,
  buildTopicOptions,
  createEmptyDraft,
  draftFromFile,
  filterExplorerNodes,
  flattenExplorerNodes,
  getCurrentPathLabel,
  getErrorMessage,
  getDraftMetadataPayload,
  getFileMetadataPayload,
  readExpandedKeys,
  slugify,
  type FileMetadataDraft,
  type TopicLabels,
  writeExpandedKeys,
} from './knowledgeWorkspace/shared';

interface HciotKnowledgeWorkspaceProps {
  active: boolean;
  language: HciotLanguage;
}

export default function HciotKnowledgeWorkspace({
  active,
  language,
}: HciotKnowledgeWorkspaceProps) {
  const statusTimerRef = useRef<number | null>(null);
  const suppressHoverRef = useRef(false);

  const [files, setFiles] = useState<HciotKnowledgeFile[]>([]);
  const [categories, setCategories] = useState<HciotTopicCategory[]>([]);
  const [selectedFileName, setSelectedFileName] = useState<string | null>(null);
  const [expandedKeys, setExpandedKeys] = useState<string[]>(() => readExpandedKeys(language));
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarHoverExpanded, setSidebarHoverExpanded] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [loadingWorkspace, setLoadingWorkspace] = useState(false);
  const [loadingContent, setLoadingContent] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState(false);
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

  const metadataDirty = useMemo(() => {
    if (!selectedFile) {
      return false;
    }
    if (draft.categoryId === NEW_VALUE || draft.topicId === NEW_VALUE) {
      return true;
    }

    const currentPayload = getFileMetadataPayload(selectedFile);
    const draftPayload = getDraftMetadataPayload(draft);
    return JSON.stringify(currentPayload) !== JSON.stringify(draftPayload);
  }, [draft, selectedFile]);

  const contentDirty = fileEditable && editorText !== originalText;
  const hasUnsavedChanges = metadataDirty || contentDirty;

  const { roots, filePathKeys } = useMemo(
    () => buildExplorerTree(files, categories, language),
    [categories, files, language],
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
      const [knowledgeResponse, topicsResponse] = await Promise.all([
        api.listHciotKnowledgeFiles(language),
        api.listHciotTopicsAdmin(),
      ]);

      const nextFiles = knowledgeResponse.files || [];
      setFiles(nextFiles);
      setCategories(topicsResponse.categories || []);
      setSelectedFileName((current) => {
        const candidate = preferredFileName ?? current;
        if (candidate && nextFiles.some((file) => file.name === candidate)) {
          return candidate;
        }
        return nextFiles[0]?.name || null;
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

  const handleSelectFile = (fileName: string) => {
    if (fileName === selectedFileName) {
      return;
    }

    if (hasUnsavedChanges) {
      const shouldDiscard = window.confirm(
        language === 'zh'
          ? '目前檔案有尚未儲存的變更，確定要切換嗎？'
          : 'You have unsaved changes. Switch files anyway?',
      );
      if (!shouldDiscard) {
        return;
      }
    }

    ensureSelectedPathExpanded(fileName);
    setSelectedFileName(fileName);
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

  const handleUploadFiles = async (
    filesToUpload: File[],
    topicId: string | null,
    labels: TopicLabels | null,
  ) => {
    if (!filesToUpload.length) return;
    setUploading(true);
    try {
      let firstUploadedFileName: string | null = null;
      for (const file of filesToUpload) {
        const response = await uploadFileWithTopic(file, topicId, labels);
        if (!firstUploadedFileName) {
          firstUploadedFileName = response.name;
        }
      }
      await refreshWorkspace(firstUploadedFileName);
      setQaDialogOpen(false);
      showStatus(
        language === 'zh'
          ? `已上傳 ${filesToUpload.length} 個檔案`
          : `Uploaded ${filesToUpload.length} file(s)`,
      );
    } catch (error) {
      console.error('Failed to upload HCIoT files:', error);
      alert(getErrorMessage(error));
    } finally {
      setUploading(false);
    }
  };

  const handleQASubmit = async (
    file: File,
    topicId: string,
    labels: TopicLabels,
  ) => {
    await handleUploadFiles([file], topicId, labels);
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
        topicId: '',
        topicLabelZh: '',
        topicLabelEn: '',
      });
      return;
    }

    const category = categoryOptions.find((item) => item.id === value);
    setDraft({
      categoryId: value,
      topicId: '',
      categoryLabelZh: category?.labels.zh || '',
      categoryLabelEn: category?.labels.en || '',
      topicLabelZh: '',
      topicLabelEn: '',
    });
  };

  const handleTopicChange = (value: string) => {
    if (!value) {
      setDraft((previous) => ({
        ...previous,
        topicId: '',
        topicLabelZh: '',
        topicLabelEn: '',
      }));
      return;
    }

    if (value === NEW_VALUE) {
      setDraft((previous) => ({
        ...previous,
        topicId: NEW_VALUE,
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
          topicId: '',
          topicLabelZh: '',
          topicLabelEn: '',
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
        visibleRows={visibleRows}
        visibleExpandedKeys={visibleExpandedKeys}
        onMouseEnter={handleSidebarMouseEnter}
        onMouseLeave={handleSidebarMouseLeave}
        onToggleSidebar={handleToggleSidebar}
        onSearchChange={setSearchQuery}
        onToggleExpanded={toggleExpanded}
        onSelectFile={handleSelectFile}
        onOpenUploadDialog={() => setQaDialogOpen(true)}
      />

      <UploadDialog
        open={qaDialogOpen}
        language={language}
        categories={categories}
        uploading={uploading}
        onClose={() => setQaDialogOpen(false)}
        onUploadFiles={handleUploadFiles}
        onSubmitQA={handleQASubmit}
      />

      <FileDetailPane
        language={language}
        selectedFile={selectedFile}
        currentPathLabel={currentPathLabel}
        statusMessage={statusMessage}
        deleting={deleting}
        saving={saving}
        uploading={uploading}
        hasUnsavedChanges={hasUnsavedChanges}
        draft={draft}
        categoryOptions={categoryOptions}
        topicOptions={topicOptions}
        fileEditable={fileEditable}
        loadingContent={loadingContent}
        contentMessage={contentMessage}
        editorText={editorText}
        onDownload={() => {
          if (selectedFile) {
            api.downloadHciotKnowledgeFile(selectedFile.name, language);
          }
        }}
        onDelete={() => {
          void handleDeleteFile();
        }}
        onSave={() => {
          void handleSave();
        }}
        onCategoryChange={handleCategoryChange}
        onTopicChange={handleTopicChange}
        onDraftChange={patchDraft}
        onEditorTextChange={setEditorText}
      />
    </section>
  );
}
