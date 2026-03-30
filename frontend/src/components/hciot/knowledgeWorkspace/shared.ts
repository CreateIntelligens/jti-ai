import type { HciotLanguage } from '../../../config/hciotTopics';
import type {
  HciotKnowledgeFile,
  HciotLabels,
  HciotTopicCategory,
} from '../../../services/api/hciot';

export const NO_TOPIC_KEY = '__no_topic__';
export const NEW_VALUE = '__new__';

export interface ExplorerFolderNode {
  key: string;
  kind: 'folder';
  label: string;
  children: ExplorerNode[];
  tone?: 'category' | 'topic';
}

export interface ExplorerFileNode {
  key: string;
  kind: 'file';
  label: string;
  file: HciotKnowledgeFile;
}

export type ExplorerNode = ExplorerFolderNode | ExplorerFileNode;

export interface ExplorerRow {
  node: ExplorerNode;
  depth: number;
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

export function isFolderNode(node: ExplorerNode): node is ExplorerFolderNode {
  return node.kind === 'folder';
}

function storageKeyForExpanded(language: HciotLanguage): string {
  return `hciot:knowledge-explorer:expanded:${language}`;
}

export function readExpandedKeys(language: HciotLanguage): string[] {
  try {
    const raw = localStorage.getItem(storageKeyForExpanded(language));
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : [];
  } catch {
    return [];
  }
}

export function writeExpandedKeys(language: HciotLanguage, keys: string[]): void {
  localStorage.setItem(storageKeyForExpanded(language), JSON.stringify(keys));
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

function matchesSearch(node: ExplorerNode, query: string): boolean {
  if (!query) {
    return true;
  }

  const normalizedQuery = query.toLowerCase();
  if (node.label.toLowerCase().includes(normalizedQuery)) {
    return true;
  }

  if (node.kind === 'file') {
    return node.file.name.toLowerCase().includes(normalizedQuery);
  }

  return false;
}

export function filterExplorerNodes(nodes: ExplorerNode[], query: string): ExplorerNode[] {
  if (!query) {
    return nodes;
  }

  return nodes.flatMap<ExplorerNode>((node) => {
    if (node.kind === 'file') {
      return matchesSearch(node, query) ? [node] : [];
    }

    const filteredChildren = filterExplorerNodes(node.children, query);
    if (matchesSearch(node, query) || filteredChildren.length > 0) {
      return [{ ...node, children: filteredChildren }];
    }

    return [];
  });
}

export function flattenExplorerNodes(
  nodes: ExplorerNode[],
  expandedKeys: Set<string>,
  query: string,
  depth = 0,
): ExplorerRow[] {
  return nodes.flatMap((node) => {
    const rows: ExplorerRow[] = [{ node, depth }];
    if (isFolderNode(node) && node.children.length > 0) {
      const shouldExpand = Boolean(query) || expandedKeys.has(node.key);
      if (shouldExpand) {
        rows.push(...flattenExplorerNodes(node.children, expandedKeys, query, depth + 1));
      }
    }
    return rows;
  });
}

export function getNoTopicLabel(language: HciotLanguage): string {
  return language === 'zh' ? '未指定主題' : 'No Topic';
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

export function getCurrentPathLabel(
  selectedFile: HciotKnowledgeFile | null,
  language: HciotLanguage,
): string {
  if (!selectedFile) {
    return language === 'zh' ? '選擇檔案開始編輯' : 'Select a file to start editing';
  }

  const categoryLabel = selectedFile[`category_label_${language}` as const] || categoryPrefix(selectedFile.topic_id);
  const topicLabel = selectedFile[`topic_label_${language}` as const] || selectedFile.topic_id;
  if (!categoryLabel && !topicLabel) {
    return language === 'zh' ? '關於元復醫院' : 'About Yuan-Fu Hospital';
  }

  return topicLabel ? `${categoryLabel} / ${topicLabel}` : categoryLabel;
}

export function buildExplorerTree(
  files: HciotKnowledgeFile[],
  categories: HciotTopicCategory[],
  language: HciotLanguage,
): { roots: ExplorerNode[]; filePathKeys: Map<string, string[]> } {
  const roots: ExplorerNode[] = [];
  const filePathKeys = new Map<string, string[]>();
  const filesByCategory = new Map<string, HciotKnowledgeFile[]>();

  files.forEach((file) => {
    const categoryId = categoryPrefix(file.topic_id);
    const group = filesByCategory.get(categoryId) || [];
    group.push(file);
    filesByCategory.set(categoryId, group);
  });

  const sortedCategoryEntries = [...filesByCategory.entries()].sort(([leftId, leftFiles], [rightId, rightFiles]) => {
    const leftCategory = categories.find((item) => item.id === leftId);
    const rightCategory = categories.find((item) => item.id === rightId);
    const leftLabel = leftCategory?.labels[language] || leftFiles[0]?.[`category_label_${language}` as const] || leftId;
    const rightLabel = rightCategory?.labels[language] || rightFiles[0]?.[`category_label_${language}` as const] || rightId;
    return sortByLabel(leftLabel, rightLabel);
  });

  sortedCategoryEntries.forEach(([categoryId, categoryFiles]) => {
    const category = categories.find((item) => item.id === categoryId);
    const categoryLabel =
      category?.labels[language] || categoryFiles[0]?.[`category_label_${language}` as const] || categoryId;
    const categoryKey = `category:${categoryId}`;
    const filesByTopic = new Map<string, HciotKnowledgeFile[]>();

    categoryFiles.forEach((file) => {
      const topicKey = file.topic_id || NO_TOPIC_KEY;
      const group = filesByTopic.get(topicKey) || [];
      group.push(file);
      filesByTopic.set(topicKey, group);
    });

    const sortedTopicEntries = [...filesByTopic.entries()].sort(([leftId, leftFiles], [rightId, rightFiles]) => {
      const leftLabel = leftId === NO_TOPIC_KEY
        ? getNoTopicLabel(language)
        : category?.topics.find((item) => item.id === leftId)?.labels[language]
          || leftFiles[0]?.[`topic_label_${language}` as const]
          || leftId;
      const rightLabel = rightId === NO_TOPIC_KEY
        ? getNoTopicLabel(language)
        : category?.topics.find((item) => item.id === rightId)?.labels[language]
          || rightFiles[0]?.[`topic_label_${language}` as const]
          || rightId;
      return sortByLabel(leftLabel, rightLabel);
    });

    const topicNodes: ExplorerNode[] = sortedTopicEntries.map(([topicId, topicFiles]) => {
      const topicLabel = topicId === NO_TOPIC_KEY
        ? getNoTopicLabel(language)
        : category?.topics.find((item) => item.id === topicId)?.labels[language]
          || topicFiles[0]?.[`topic_label_${language}` as const]
          || topicId;
      const topicKey = `topic:${topicId}`;
      const fileNodes = topicFiles
        .slice()
        .sort((left, right) => sortByLabel(getFileLabel(left), getFileLabel(right)))
        .map((file) => {
          filePathKeys.set(file.name, [categoryKey, topicKey]);
          return {
            key: `file:${file.name}`,
            kind: 'file',
            label: getFileLabel(file),
            file,
          } satisfies ExplorerFileNode;
        });

      return {
        key: topicKey,
        kind: 'folder',
        label: topicLabel,
        tone: 'topic',
        children: fileNodes,
      } satisfies ExplorerFolderNode;
    });

    roots.push({
      key: categoryKey,
      kind: 'folder',
      label: categoryLabel,
      tone: 'category',
      children: topicNodes,
    });
  });

  return { roots, filePathKeys };
}
