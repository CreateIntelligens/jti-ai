import type { HciotLanguage } from '../../../config/hciotTopics';
import type {
  HciotKnowledgeFile,
  HciotTopicCategory,
} from '../../../services/api/hciot';
import { toErrorMessage } from '../../../utils/errors';

export const NO_TOPIC_KEY = '__no_topic__';
export const NEW_VALUE = '__new__';

export interface TopicLabels {
  categoryLabel: string;
  topicLabel: string;
}

export interface FileMetadataDraft {
  categoryId: string;
  topicId: string;
  categoryLabel: string;
  topicLabel: string;
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

/**
 * Trims a single-language label. Returns null when the result is empty so
 * callers can validate required labels.
 */
export function normalizeLabel(value: string): string | null {
  const trimmed = value.trim();
  return trimmed || null;
}

export const DEFAULT_TOPIC_LABEL = '預設主題';

export function missingLabelMessage(
  kind: 'category' | 'topic',
  language: HciotLanguage,
): string {
  if (language === 'zh') {
    return kind === 'category' ? '新增科別需要名稱' : '新增主題需要名稱';
  }
  return kind === 'category'
    ? 'New categories require a label'
    : 'New topics require a label';
}

export function createEmptyDraft(): FileMetadataDraft {
  return {
    categoryId: '',
    topicId: '',
    categoryLabel: '',
    topicLabel: '',
  };
}

export function getFileLabel(file: HciotKnowledgeFile): string {
  return (file.display_name || file.name || '').trim() || file.name;
}

function getCategoryLabel(
  file: HciotKnowledgeFile,
  category?: HciotTopicCategory,
): string {
  return category?.label || file.category_label || '';
}

function getTopicLabel(
  file: HciotKnowledgeFile,
  category?: HciotTopicCategory,
): string {
  const topic = category?.topics.find((item) => item.id === file.topic_id);
  return topic?.label || file.topic_label || '';
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

  return {
    categoryId,
    topicId: file.topic_id || '',
    categoryLabel: getCategoryLabel(file, category),
    topicLabel: getTopicLabel(file, category),
  };
}

export function getMetadataPayload(
  data: HciotKnowledgeFile | FileMetadataDraft,
) {
  // Common logic for both HciotKnowledgeFile and FileMetadataDraft.
  // Output uses the flattened single-label shape and only emits the label
  // for the file's own language partition.
  const isDraft = 'categoryId' in data;
  let categoryId: string | null = null;
  let topicId: string | null = null;

  if (isDraft) {
    const draft = data as FileMetadataDraft;
    if (draft.categoryId && draft.categoryId !== NEW_VALUE) {
      categoryId = draft.categoryId;
    }
    if (categoryId && draft.topicId && draft.topicId !== NEW_VALUE) {
      topicId = draft.topicId;
    }
  } else {
    const file = data as HciotKnowledgeFile;
    if (file.topic_id) {
      categoryId = categoryPrefix(file.topic_id);
      topicId = file.topic_id;
    }
  }

  if (isDraft) {
    return {
      topic_id: topicId,
      category_label: categoryId ? data.categoryLabel.trim() || null : null,
      topic_label: topicId ? data.topicLabel.trim() || null : null,
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

function buildGenericOptions<T extends { id: string; label: string }>(
  items: T[],
  selectedId: string,
  label: string,
  extraDefaults: Partial<T> = {},
): T[] {
  const sorted = [...items].sort((a, b) => sortByLabel(a.label, b.label));

  if (!selectedId || selectedId === NEW_VALUE || sorted.some(i => i.id === selectedId)) {
    return sorted;
  }

  return [
    ...sorted,
    {
      ...extraDefaults,
      id: selectedId,
      label: label || selectedId,
    } as T
  ];
}

export function buildCategoryOptions(
  categories: HciotTopicCategory[],
  draft: FileMetadataDraft,
): HciotTopicCategory[] {
  return buildGenericOptions(categories, draft.categoryId, draft.categoryLabel, { topics: [] });
}

export function buildTopicOptions(
  currentCategory: HciotTopicCategory | null,
  draft: FileMetadataDraft,
): TopicOption[] {
  if (!currentCategory) {
    if (!draft.topicId || draft.topicId === NEW_VALUE) {
      return [];
    }
    return [{
      id: draft.topicId,
      label: draft.topicLabel || draft.topicId,
      questions: [],
    }];
  }

  return buildGenericOptions(currentCategory.topics, draft.topicId, draft.topicLabel, { questions: [] });
}

export function createEmptyTopicDraft(): Pick<FileMetadataDraft, 'topicId' | 'topicLabel'> {
  return {
    topicId: '',
    topicLabel: '',
  };
}

export interface ParsedExplorerKey {
  kind: string;
  id: string;
}

export function parseExplorerKey(key: string): ParsedExplorerKey {
  const separatorIndex = key.indexOf(':');
  return separatorIndex === -1
    ? { kind: key, id: '' }
    : { kind: key.slice(0, separatorIndex), id: key.slice(separatorIndex + 1) };
}

export function splitTopicId(topicId: string): { categoryId: string; topicSlug: string } {
  const [categoryId = '', ...topicParts] = topicId.split('/');
  return { categoryId, topicSlug: topicParts.join('/') };
}

export function moveItem<T>(items: T[], from: number, to: number): T[] | null {
  if (from === -1 || to === -1) {
    return null;
  }

  const nextItems = [...items];
  const [moved] = nextItems.splice(from, 1);
  nextItems.splice(to, 0, moved);
  return nextItems;
}
