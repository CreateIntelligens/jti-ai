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
    zh: zhLabel,
    en: enLabel,
  };
}

export const DEFAULT_TOPIC_LABELS: HciotLabels = { zh: '預設主題', en: 'Default topic' };

export function missingBilingualLabelMessage(
  kind: 'category' | 'topic',
  language: HciotLanguage,
): string {
  if (language === 'zh') {
    return kind === 'category' ? '新增科別需要中英文名稱' : '新增主題需要中英文名稱';
  }
  return kind === 'category'
    ? 'New categories require both zh and en labels'
    : 'New topics require both zh and en labels';
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

export function getMetadataPayload(data: HciotKnowledgeFile | FileMetadataDraft) {
  // Common logic for both HciotKnowledgeFile and FileMetadataDraft
  const isDraft = 'categoryId' in data;
  const categoryId = isDraft
    ? (data.categoryId && data.categoryId !== NEW_VALUE ? data.categoryId : null)
    : (data.topic_id ? categoryPrefix(data.topic_id) : null);

  const topicId = isDraft
    ? (categoryId && data.topicId && data.topicId !== NEW_VALUE ? data.topicId : null)
    : data.topic_id;

  if (isDraft) {
    return {
      topic_id: topicId,
      category_label_zh: categoryId ? data.categoryLabelZh.trim() || null : null,
      category_label_en: categoryId ? data.categoryLabelEn.trim() || null : null,
      topic_label_zh: topicId ? data.topicLabelZh.trim() || null : null,
      topic_label_en: topicId ? data.topicLabelEn.trim() || null : null,
    };
  }

  return {
    topic_id: topicId,
    category_label_zh: data.category_label_zh || null,
    category_label_en: data.category_label_en || null,
    topic_label_zh: data.topic_label_zh || null,
    topic_label_en: data.topic_label_en || null,
  };
}

export function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function buildGenericOptions<T extends { id: string; labels: HciotLabels }>(
  items: T[],
  selectedId: string,
  labels: { zh: string; en: string },
  language: HciotLanguage,
  extraDefaults: Partial<T> = {},
): T[] {
  const sorted = [...items].sort((a, b) => sortByLabel(a.labels[language], b.labels[language]));

  if (!selectedId || selectedId === NEW_VALUE || sorted.some(i => i.id === selectedId)) {
    return sorted;
  }

  return [
    ...sorted,
    {
      ...extraDefaults,
      id: selectedId,
      labels: {
        zh: labels.zh || selectedId,
        en: labels.en || selectedId,
      },
    } as T
  ];
}

export function buildCategoryOptions(
  categories: HciotTopicCategory[],
  draft: FileMetadataDraft,
  language: HciotLanguage,
): HciotTopicCategory[] {
  return buildGenericOptions(categories, draft.categoryId, {
    zh: draft.categoryLabelZh,
    en: draft.categoryLabelEn
  }, language, { topics: [] });
}

export function buildTopicOptions(
  currentCategory: HciotTopicCategory | null,
  draft: FileMetadataDraft,
  language: HciotLanguage,
): TopicOption[] {
  if (!currentCategory) {
    if (!draft.topicId || draft.topicId === NEW_VALUE) {
      return [];
    }
    return [{
      id: draft.topicId,
      labels: {
        zh: draft.topicLabelZh || draft.topicId,
        en: draft.topicLabelEn || draft.topicId,
      },
      questions: { zh: [], en: [] },
    }];
  }

  return buildGenericOptions(currentCategory.topics, draft.topicId, {
    zh: draft.topicLabelZh,
    en: draft.topicLabelEn
  }, language, { questions: { zh: [], en: [] } });
}
