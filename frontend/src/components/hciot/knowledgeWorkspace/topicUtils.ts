import type { HciotLanguage } from '../../../config/hciotTopics';
import type {
  HciotKnowledgeFile,
  HciotLabels,
  HciotTopicCategory,
} from '../../../services/api/hciot';

export const NO_TOPIC_KEY = '__no_topic__';
export const NEW_VALUE = '__new__';

export interface TopicLabels {
  categoryLabelZh: string;
  categoryLabelEn: string;
  topicLabelZh: string;
  topicLabelEn: string;
}

export interface FileMetadataDraft {
  categoryId: string;
  topicId: string;
  categoryLabelZh: string;
  categoryLabelEn: string;
  topicLabelZh: string;
  topicLabelEn: string;
}

export type TopicOption = HciotTopicCategory['topics'][number];
export type CategoryOption = HciotTopicCategory;

export function slugify(text: string): string {
  return text
    .normalize('NFKC')
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, '-')
    .replace(/^-+|-+$/g, '');
}

export function sortByLabel(left: string, right: string): number {
  return left.localeCompare(right, undefined, { numeric: true, sensitivity: 'base' });
}

export function buildLabels(zh: string, en: string): HciotLabels | null {
  const zhLabel = zh.trim();
  const enLabel = en.trim();
  if (!zhLabel && !enLabel) {
    return null;
  }

  return {
    zh: zhLabel || enLabel,
    en: enLabel || zhLabel,
  };
}

export function createEmptyDraft(): FileMetadataDraft {
  return {
    categoryId: '',
    topicId: '',
    categoryLabelZh: '',
    categoryLabelEn: '',
    topicLabelZh: '',
    topicLabelEn: '',
  };
}
export function getFileLabel(file: HciotKnowledgeFile): string {
  return (file.display_name || file.name || '').trim() || file.name;
}

function getCategoryLabels(file: HciotKnowledgeFile, category?: HciotTopicCategory): HciotLabels {
  return {
    zh: category?.labels.zh || file.category_label_zh || '',
    en: category?.labels.en || file.category_label_en || '',
  };
}

function getTopicLabels(file: HciotKnowledgeFile, category?: HciotTopicCategory): HciotLabels {
  const topic = category?.topics.find((item) => item.id === file.topic_id);
  return {
    zh: topic?.labels.zh || file.topic_label_zh || '',
    en: topic?.labels.en || file.topic_label_en || '',
  };
}

export function categoryPrefix(topicId: string | null | undefined): string {
  if (!topicId) {
    return '';
  }

  const separatorIndex = topicId.indexOf('/');
  return separatorIndex < 0 ? topicId : topicId.slice(0, separatorIndex);
}

export function draftFromFile(
  file: HciotKnowledgeFile,
  categories: HciotTopicCategory[],
): FileMetadataDraft {
  const categoryId = categoryPrefix(file.topic_id);
  const category = categories.find((item) => item.id === categoryId);
  const categoryLabels = getCategoryLabels(file, category);
  const topicLabels = getTopicLabels(file, category);

  return {
    categoryId,
    topicId: file.topic_id || '',
    categoryLabelZh: categoryLabels.zh,
    categoryLabelEn: categoryLabels.en,
    topicLabelZh: topicLabels.zh,
    topicLabelEn: topicLabels.en,
  };
}

export function getFileMetadataPayload(file: HciotKnowledgeFile) {
  return {
    topic_id: file.topic_id || null,
    category_label_zh: file.category_label_zh || null,
    category_label_en: file.category_label_en || null,
    topic_label_zh: file.topic_label_zh || null,
    topic_label_en: file.topic_label_en || null,
  };
}

export function getDraftMetadataPayload(draft: FileMetadataDraft) {
  const categoryId = draft.categoryId && draft.categoryId !== NEW_VALUE ? draft.categoryId : null;
  const topicId = categoryId && draft.topicId && draft.topicId !== NEW_VALUE ? draft.topicId : null;

  return {
    topic_id: topicId,
    category_label_zh: categoryId ? draft.categoryLabelZh.trim() || null : null,
    category_label_en: categoryId ? draft.categoryLabelEn.trim() || null : null,
    topic_label_zh: topicId ? draft.topicLabelZh.trim() || null : null,
    topic_label_en: topicId ? draft.topicLabelEn.trim() || null : null,
  };
}
export function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function buildCategoryOptions(
  categories: HciotTopicCategory[],
  draft: FileMetadataDraft,
  language: HciotLanguage,
): CategoryOption[] {
  const sortedCategories = categories
    .slice()
    .sort((left, right) => sortByLabel(left.labels[language], right.labels[language]));

  const hasCurrentCategory = draft.categoryId
    && draft.categoryId !== NEW_VALUE
    && sortedCategories.some((category) => category.id === draft.categoryId);

  if (!hasCurrentCategory && draft.categoryId) {
    return [
      ...sortedCategories,
      {
        id: draft.categoryId,
        labels: {
          zh: draft.categoryLabelZh || draft.categoryId,
          en: draft.categoryLabelEn || draft.categoryId,
        },
        topics: [],
      },
    ];
  }

  return sortedCategories;
}

export function buildTopicOptions(
  currentCategory: HciotTopicCategory | null,
  draft: FileMetadataDraft,
  language: HciotLanguage,
): TopicOption[] {
  if (!currentCategory) {
    if (draft.topicId && draft.topicId !== NEW_VALUE) {
      return [{
        id: draft.topicId,
        labels: {
          zh: draft.topicLabelZh || draft.topicId,
          en: draft.topicLabelEn || draft.topicId,
        },
        questions: { zh: [], en: [] },
      }];
    }
    return [];
  }

  const sortedTopics = currentCategory.topics
    .slice()
    .sort((left, right) => sortByLabel(left.labels[language], right.labels[language]));

  const hasCurrentTopic = draft.topicId
    && draft.topicId !== NEW_VALUE
    && sortedTopics.some((topic) => topic.id === draft.topicId);

  if (!hasCurrentTopic && draft.topicId) {
    return [
      ...sortedTopics,
      {
        id: draft.topicId,
        labels: {
          zh: draft.topicLabelZh || draft.topicId,
          en: draft.topicLabelEn || draft.topicId,
        },
        questions: { zh: [], en: [] },
      },
    ];
  }

  return sortedTopics;
}
