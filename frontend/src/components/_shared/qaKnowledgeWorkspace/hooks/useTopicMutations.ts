import { useMemo, useState } from 'react';
import type { QaLanguage, QaAdminCategory } from '../../../../config/qaTopics';
import type { QaKnowledgeFile } from '../../../../services/api/_shared/qaKnowledge';
import type { QaWorkspaceApiClient } from '../QaKnowledgeWorkspace';
import {
  NEW_VALUE,
  buildCategoryOptions,
  buildTopicOptions,
  categoryPrefix,
  createEmptyDraft,
  createEmptyTopicDraft,
  getErrorMessage,
  moveItem,
  parseExplorerKey,
  type FileMetadataDraft,
} from '../topicUtils';

export interface UseTopicMutationsOptions {
  api: QaWorkspaceApiClient;
  language: QaLanguage;
  files: QaKnowledgeFile[];
  categories: QaAdminCategory[];
  draft: FileMetadataDraft;
  setDraft: React.Dispatch<React.SetStateAction<FileMetadataDraft>>;
  patchDraft: (changes: Partial<FileMetadataDraft>) => void;
  selectedFileName: string | null;
  setSelectedFileName: (name: string | null) => void;
  selectedMergedTopicId: string | null;
  setSelectedMergedTopicId: (name: string | null) => void;
  refreshWorkspaceAfterTopicChange: (preferredFileName?: string | null) => Promise<void>;
  showStatus: (message: string) => void;
  discardChanges: () => boolean;
  text: (zh: string, en: string) => string;
}

export function useTopicMutations({
  api,
  language,
  files,
  categories,
  draft,
  setDraft,
  patchDraft,
  selectedFileName,
  setSelectedFileName,
  selectedMergedTopicId,
  setSelectedMergedTopicId,
  refreshWorkspaceAfterTopicChange,
  showStatus,
  discardChanges,
  text,
}: UseTopicMutationsOptions) {
  const [renamingKey, setRenamingKey] = useState<string | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [deletingTopic, setDeletingTopic] = useState(false);

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

  const handleDeleteTopic = async (topicId: string, topicLabel: string) => {
    const targets = files.filter((file) => file.topic_id === topicId);
    if (!targets.length) return;
    const confirmed = window.confirm(text(
      `確定要刪除主題「${topicLabel}」？無法復原。`,
      `Delete topic "${topicLabel}"? This cannot be undone.`,
    ));
    if (!confirmed) return;

    setDeletingTopic(true);
    try {
      const results = await Promise.allSettled(
        targets.map((file) => api.deleteKnowledgeFile(file.name, language)),
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
      console.error('Failed to delete topic:', error);
      alert(getErrorMessage(error));
    } finally {
      setDeletingTopic(false);
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
        topicIds.map((topicId) => api.updateTopic(topicId, payload, language)),
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
      console.error('Failed to rename category/topic:', error);
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

    let orderedCategories: QaAdminCategory[] | null = null;

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
      await api.reorderTopics(topicIds, language);
      await refreshWorkspaceAfterTopicChange(selectedFileName);
      showStatus(text('順序已更新', 'Order updated'));
    } catch (error) {
      console.error('Failed to reorder topics:', error);
      alert(getErrorMessage(error));
    }
  };

  return {
    renamingKey,
    setRenamingKey,
    renaming,
    deletingTopic,
    topicOptions,
    categoryOptions,
    handleCategoryChange,
    handleTopicChange,
    handleDeleteTopic,
    handleStartRename,
    handleCancelRename,
    handleCommitRename,
    handleReorder,
  };
}
