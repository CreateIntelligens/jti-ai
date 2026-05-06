import type { HciotLanguage } from '../../../config/hciotTopics';
import type {
  HciotKnowledgeFile,
  HciotLabels,
  HciotTopicCategory,
} from '../../../services/api/hciot';
import { toErrorMessage } from '../../../utils/errors';

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
  const leftPriority = labelSortPriority(left);
  const rightPriority = labelSortPriority(right);
  if (leftPriority !== rightPriority) {
    return leftPriority - rightPriority;
  }

  return left.localeCompare(right, undefined, { numeric: true, sensitivity: 'base' });
}

const FIRST_TOPIC_LABELS = new Set([
  '常見問題',
  'faq',
  'common questions',
  'frequently asked questions',
]);

function labelSortPriority(label: string): number {
  const normalized = label.normalize('NFKC').trim().toLowerCase();
  return FIRST_TOPIC_LABELS.has(normalized) ? 0 : 1;
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

function buildDraftLabels(
  language: HciotLanguage,
  fileLabel: string,
  topicStoreLabels?: HciotLabels,
): HciotLabels {
  if (language === 'zh') {
    return {
      zh: topicStoreLabels?.zh || fileLabel,
      en: topicStoreLabels?.en || '',
    };
  }
  return {
    zh: topicStoreLabels?.zh || '',
    en: topicStoreLabels?.en || fileLabel,
  };
}

function getCategoryLabels(
  file: HciotKnowledgeFile,
  language: HciotLanguage,
  category?: HciotTopicCategory,
): HciotLabels {
  return buildDraftLabels(language, file.category_label || '', category?.labels);
}

function getTopicLabels(
  file: HciotKnowledgeFile,
  language: HciotLanguage,
  category?: HciotTopicCategory,
): HciotLabels {
  const topic = category?.topics.find((item) => item.id === file.topic_id);
  return buildDraftLabels(language, file.topic_label || '', topic?.labels);
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
  language: HciotLanguage,
): FileMetadataDraft {
  const categoryId = categoryPrefix(file.topic_id);
  const category = categories.find((item) => item.id === categoryId);
  const categoryLabels = getCategoryLabels(file, language, category);
  const topicLabels = getTopicLabels(file, language, category);

  return {
    categoryId,
    topicId: file.topic_id || '',
    categoryLabelZh: categoryLabels.zh,
    categoryLabelEn: categoryLabels.en,
    topicLabelZh: topicLabels.zh,
    topicLabelEn: topicLabels.en,
  };
}

export function getMetadataPayload(
  data: HciotKnowledgeFile | FileMetadataDraft,
  language: HciotLanguage,
) {
  // Common logic for both HciotKnowledgeFile and FileMetadataDraft.
  // Output uses the flattened single-label shape and only emits the label
  // for the file's own language partition (`language`).
  const isDraft = 'categoryId' in data;
  const categoryId = isDraft
    ? (data.categoryId && data.categoryId !== NEW_VALUE ? data.categoryId : null)
    : (data.topic_id ? categoryPrefix(data.topic_id) : null);

  const topicId = isDraft
    ? (categoryId && data.topicId && data.topicId !== NEW_VALUE ? data.topicId : null)
    : data.topic_id;

  if (isDraft) {
    const draftCategoryLabel = language === 'zh' ? data.categoryLabelZh : data.categoryLabelEn;
    const draftTopicLabel = language === 'zh' ? data.topicLabelZh : data.topicLabelEn;
    return {
      topic_id: topicId,
      category_label: categoryId ? draftCategoryLabel.trim() || null : null,
      topic_label: topicId ? draftTopicLabel.trim() || null : null,
    };
  }

  return {
    topic_id: topicId,
    category_label: data.category_label || null,
    topic_label: data.topic_label || null,
  };
}

export function getErrorMessage(error: unknown): string {
  return toErrorMessage(error);
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
