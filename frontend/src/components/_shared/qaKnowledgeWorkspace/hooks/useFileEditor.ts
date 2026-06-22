import { useEffect, useMemo, useState } from 'react';
import type { QaLanguage, QaAdminCategory } from '../../../../config/qaTopics';
import type { QaKnowledgeFile } from '../../../../services/api/_shared/qaKnowledge';
import type { QaWorkspaceApiClient } from '../QaKnowledgeWorkspace';
import {
  NEW_VALUE,
  createEmptyDraft,
  createEmptyTopicDraft,
  draftFromFile,
  getErrorMessage,
  getMetadataPayload,
  normalizeLabel,
  slugify,
  type FileMetadataDraft,
} from '../topicUtils';

export interface UseFileEditorOptions {
  api: QaWorkspaceApiClient;
  language: QaLanguage;
  selectedFileName: string | null;
  setSelectedFileName: (name: string | null) => void;
  setSelectedImageName: (name: string | null) => void;
  setSelectedMergedTopicId: (name: string | null) => void;
  selectedFile: QaKnowledgeFile | null;
  categories: QaAdminCategory[];
  setFiles: React.Dispatch<React.SetStateAction<QaKnowledgeFile[]>>;
  refreshWorkspaceAfterTopicChange: (preferredFileName?: string | null) => Promise<void>;
  showStatus: (message: string) => void;
  ensureSelectedPathExpanded: (fileName: string) => void;
  text: (zh: string, en: string) => string;
}

export function useFileEditor({
  api,
  language,
  selectedFileName,
  setSelectedFileName,
  setSelectedImageName,
  setSelectedMergedTopicId,
  selectedFile,
  categories,
  setFiles,
  refreshWorkspaceAfterTopicChange,
  showStatus,
  ensureSelectedPathExpanded,
  text,
}: UseFileEditorOptions) {
  const [editorText, setEditorText] = useState('');
  const [originalText, setOriginalText] = useState('');
  const [fileEditable, setFileEditable] = useState(false);
  const [loadingContent, setLoadingContent] = useState(false);
  const [contentMessage, setContentMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [draft, setDraft] = useState<FileMetadataDraft>(createEmptyDraft());

  const patchDraft = (changes: Partial<FileMetadataDraft>) => {
    setDraft((previous) => ({ ...previous, ...changes }));
  };

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
    api.getKnowledgeFileContent(selectedFileName, language)
      .then((response) => {
        if (cancelled) return;
        const nextContent = response.content || '';
        setOriginalText(nextContent);
        setEditorText(nextContent);
        setFileEditable(Boolean(response.editable));
        setContentMessage(response.message || null);
      })
      .catch((error) => {
        console.error('Failed to load file content:', error);
        if (cancelled) return;
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

  const handleSelectFile = (fileName: string) => {
    if (fileName === selectedFileName || !discardChanges()) return;
    ensureSelectedPathExpanded(fileName);
    selectWorkspaceItem({ fileName });
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
    await api.createTopic(fullTopicId, topicLabel, categoryLabel, undefined, language);
    await refreshWorkspaceAfterTopicChange(selectedFileName);

    return {
      ...nextDraft,
      topicId: fullTopicId,
      topicLabel,
    };
  };

  const handleSave = async () => {
    if (!selectedFile) return;

    setSaving(true);
    try {
      const nextDraft = await resolveDraftBeforeSave(draft);

      if (metadataDirty || draft.categoryId === NEW_VALUE || draft.topicId === NEW_VALUE) {
        const updatedMetadata = await api.updateKnowledgeFileMetadata(
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
        await api.updateKnowledgeFileContent(selectedFile.name, editorText, language);
        setOriginalText(editorText);
      }

      setDraft(nextDraft);
      await refreshWorkspaceAfterTopicChange(selectedFile.name);
      showStatus(text('變更已儲存', 'Changes saved'));
    } catch (error) {
      console.error('Failed to save file changes:', error);
      alert(getErrorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteFile = async () => {
    if (!selectedFile) return;

    const confirmed = window.confirm(text(
      `確定要刪除 ${selectedFile.display_name || selectedFile.name}？`,
      `Delete ${selectedFile.display_name || selectedFile.name}?`,
    ));
    if (!confirmed) return;

    setDeleting(true);
    try {
      await api.deleteKnowledgeFile(selectedFile.name, language);
      await refreshWorkspaceAfterTopicChange();
      showStatus(text('檔案已刪除', 'File deleted'));
    } catch (error) {
      console.error('Failed to delete file:', error);
      alert(getErrorMessage(error));
    } finally {
      setDeleting(false);
    }
  };

  return {
    editorText,
    setEditorText,
    originalText,
    setOriginalText,
    fileEditable,
    loadingContent,
    contentMessage,
    saving,
    setSaving,
    deleting,
    draft,
    setDraft,
    patchDraft,
    metadataDirty,
    contentDirty,
    hasUnsavedChanges,
    discardChanges,
    selectWorkspaceItem,
    handleSelectFile,
    handleSave,
    handleDeleteFile,
  };
}
