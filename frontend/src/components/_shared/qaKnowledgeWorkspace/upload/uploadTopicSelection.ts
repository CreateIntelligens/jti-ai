import { useEffect, useMemo, useState } from 'react';

import type { QaAdminCategory } from '../../../../config/qaTopics';
import { NEW_VALUE, normalizeLabel, slugify } from '../topicUtils';
import type { ResolvedUploadTopic } from './types';

const LS_CATEGORY_KEY = 'hciot_upload_category';
const LS_TOPIC_KEY = 'hciot_upload_topic';

interface SavedTopicSelection {
  categoryId: string;
  topicId: string;
}

export type UploadTopicOption = { value: string; label: string };

export function readSavedTopicSelection(categories: QaAdminCategory[]): SavedTopicSelection {
  if (!categories.length) {
    return { categoryId: NEW_VALUE, topicId: NEW_VALUE };
  }

  const savedCategory = localStorage.getItem(LS_CATEGORY_KEY);
  const category = (savedCategory
    ? categories.find((item) => item.id === savedCategory)
    : undefined) ?? categories[0];
  const categoryId = category.id;

  const savedTopic = localStorage.getItem(LS_TOPIC_KEY);
  const matchedSavedTopic = savedTopic
    ? category.topics.find((topic) => topic.id === savedTopic)
    : undefined;
  const topicId = matchedSavedTopic?.id
    ?? category.topics[0]?.id
    ?? NEW_VALUE;

  return { categoryId, topicId };
}

export function isUploadTopicSelectDisabled(categoryId: string): boolean {
  return !categoryId;
}

export function buildUploadTopicOptions(
  categoryId: string,
  sortedTopics: QaAdminCategory['topics'],
): UploadTopicOption[] {
  return [
    ...sortedTopics.map((topic) => ({ value: topic.id, label: topic.label })),
    ...(categoryId ? [{ value: NEW_VALUE, label: '＋ 新增主題' }] : []),
  ];
}

function firstTopicId(category: QaAdminCategory | undefined): string {
  return category?.topics[0]?.id ?? NEW_VALUE;
}

function resolveTopicInfo(
  categoryId: string,
  topicId: string,
  newCategoryLabel: string,
  newTopicLabel: string,
  currentCategory: QaAdminCategory | null | undefined,
): ResolvedUploadTopic | null {
  if (!categoryId) return null;

  let catId = categoryId;
  let categoryLabel = '';

  if (categoryId === NEW_VALUE) {
    const normalized = normalizeLabel(newCategoryLabel);
    if (!normalized) return null;
    categoryLabel = normalized;
    catId = slugify(categoryLabel);
  } else {
    if (!currentCategory) return null;
    categoryLabel = currentCategory.label;
  }

  let topSlug = '';
  let topicLabel = '';

  if (topicId === NEW_VALUE) {
    const normalized = normalizeLabel(newTopicLabel);
    if (normalized) {
      topicLabel = normalized;
      topSlug = slugify(topicLabel);
    }
  } else if (topicId && currentCategory) {
    const existing = currentCategory.topics.find((topic) => topic.id === topicId);
    if (existing) {
      topSlug = topicId.split('/').pop() || topicId;
      topicLabel = existing.label;
    }
  }

  return {
    fullTopicId: topSlug ? `${catId}/${topSlug}` : catId,
    labels: {
      categoryLabel,
      topicLabel,
    },
  };
}

export function useUploadTopicSelection(categories: QaAdminCategory[], open: boolean) {
  const [categoryId, setCategoryId] = useState(NEW_VALUE);
  const [topicId, setTopicId] = useState(NEW_VALUE);
  const [newCategoryLabel, setNewCategoryLabel] = useState('');
  const [newTopicLabel, setNewTopicLabel] = useState('');

  useEffect(() => {
    if (!open) return;
    const savedSelection = readSavedTopicSelection(categories);
    setCategoryId(savedSelection.categoryId);
    setTopicId(savedSelection.topicId);
    setNewCategoryLabel('');
    setNewTopicLabel('');
  }, [open, categories]);

  // Preserve the backend ordering (by stored `order`) so the upload dropdown
  // matches the quick-QA topic order. Both come from /topics/{lang}/all, which
  // is already sorted by `order`.
  const sortedCategories = categories;

  const currentCategory = useMemo(
    () => (categoryId && categoryId !== NEW_VALUE ? categories.find((c) => c.id === categoryId) : null),
    [categories, categoryId],
  );

  const sortedTopics = useMemo(
    () => (currentCategory ? currentCategory.topics : []),
    [currentCategory],
  );

  const resolvedTopic = useMemo(
    () => resolveTopicInfo(categoryId, topicId, newCategoryLabel, newTopicLabel, currentCategory),
    [categoryId, topicId, newCategoryLabel, newTopicLabel, currentCategory],
  );

  const hasIncompleteNewLabels = (
    (categoryId === NEW_VALUE && !normalizeLabel(newCategoryLabel))
    || (topicId === NEW_VALUE && !normalizeLabel(newTopicLabel))
  );

  return {
    categoryId,
    topicId,
    newCategoryLabel,
    newTopicLabel,
    setNewCategoryLabel,
    setNewTopicLabel,
    sortedCategories,
    sortedTopics,
    handleCategoryChange: (value: string) => {
      setCategoryId(value);
      setNewTopicLabel('');
      if (value === NEW_VALUE) {
        setTopicId(NEW_VALUE);
        localStorage.removeItem(LS_CATEGORY_KEY);
        localStorage.removeItem(LS_TOPIC_KEY);
        return;
      }

      const nextTopicId = firstTopicId(categories.find((item) => item.id === value));
      setTopicId(nextTopicId);
      setNewCategoryLabel('');
      localStorage.setItem(LS_CATEGORY_KEY, value);
      if (nextTopicId !== NEW_VALUE) {
        localStorage.setItem(LS_TOPIC_KEY, nextTopicId);
      } else {
        localStorage.removeItem(LS_TOPIC_KEY);
      }
    },
    handleTopicChange: (value: string) => {
      setTopicId(value);
      if (value !== NEW_VALUE) {
        setNewTopicLabel('');
        localStorage.setItem(LS_TOPIC_KEY, value);
      }
    },
    hasIncompleteNewLabels,
    resolvedTopic,
  };
}

export type UploadTopicSelection = ReturnType<typeof useUploadTopicSelection>;
