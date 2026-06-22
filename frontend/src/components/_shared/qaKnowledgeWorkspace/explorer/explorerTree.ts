import type { QaLanguage, QaAdminCategory } from '../../../../config/qaTopics';
import type { QaImage, QaKnowledgeFile } from '../../../../services/api/_shared/qaKnowledge';
import { NO_TOPIC_KEY, categoryPrefix, getFileLabel, sortByLabel } from '../topicUtils';

export interface ExplorerFolderNode {
  key: string;
  kind: 'folder';
  label: string;
  children: ExplorerNode[];
  tone?: 'category' | 'topic';
  topicId?: string;
}

export interface ExplorerFileNode {
  key: string;
  kind: 'file';
  label: string;
  file: QaKnowledgeFile;
}

export interface ExplorerMergedCsvNode {
  key: string;
  kind: 'merged-csv';
  label: string;
  topicId: string;
  csvCount: number;
}

export interface ExplorerImageNode {
  key: string;
  kind: 'image';
  label: string;
  image: QaImage;
}

export type ExplorerNode = ExplorerFolderNode | ExplorerFileNode | ExplorerImageNode | ExplorerMergedCsvNode;

const DOCUMENT_CATEGORY_KEY = 'category:__documents__';

export interface ExplorerRow {
  node: ExplorerNode;
  depth: number;
}

export function isFolderNode(node: ExplorerNode): node is ExplorerFolderNode {
  return node.kind === 'folder';
}

function storageKeyForExpanded(language: QaLanguage): string {
  return `hciot:knowledge-explorer:expanded:${language}`;
}

export function readExpandedKeys(language: QaLanguage): string[] {
  try {
    const raw = localStorage.getItem(storageKeyForExpanded(language));
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) {
      return [];
    }

    return parsed.filter((item): item is string => typeof item === 'string');
  } catch {
    return [];
  }
}

export function writeExpandedKeys(language: QaLanguage, keys: string[]): void {
  localStorage.setItem(storageKeyForExpanded(language), JSON.stringify(keys));
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

  if (node.kind === 'image') {
    return node.image.image_id.toLowerCase().includes(normalizedQuery);
  }

  return false;
}

export function filterExplorerNodes(nodes: ExplorerNode[], query: string): ExplorerNode[] {
  if (!query) {
    return nodes;
  }

  return nodes.flatMap<ExplorerNode>((node) => {
    if (node.kind === 'file' || node.kind === 'image' || node.kind === 'merged-csv') {
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

export function getNoTopicLabel(_language: QaLanguage): string {
  return '未指定主題';
}

function isCsvFile(file: QaKnowledgeFile): boolean {
  return (file.name || '').toLowerCase().endsWith('.csv');
}

function sortFilesByDisplayLabel(files: QaKnowledgeFile[]): QaKnowledgeFile[] {
  return files.slice().sort((left, right) => sortByLabel(getFileLabel(left), getFileLabel(right)));
}

function createFileNode(file: QaKnowledgeFile): ExplorerFileNode {
  return {
    key: `file:${file.name}`,
    kind: 'file',
    label: getFileLabel(file),
    file,
  };
}

function appendFileNode(
  nodes: ExplorerNode[],
  filePathKeys: Map<string, string[]>,
  file: QaKnowledgeFile,
  pathKeys: string[],
): void {
  filePathKeys.set(file.name, pathKeys);
  nodes.push(createFileNode(file));
}

export function getCurrentPathLabel(
  selectedFile: QaKnowledgeFile | null,
  _language: QaLanguage,
): string {
  if (!selectedFile) {
    return '選擇檔案開始編輯';
  }

  if (!selectedFile.topic_id) {
    return '文件';
  }

  const categoryLabel = selectedFile.category_label || categoryPrefix(selectedFile.topic_id);
  const topicLabel = selectedFile.topic_label || selectedFile.topic_id;
  return topicLabel ? `${categoryLabel} / ${topicLabel}` : categoryLabel;
}

export function buildExplorerTree(
  files: QaKnowledgeFile[],
  categories: QaAdminCategory[],
  language: QaLanguage,
  images: QaImage[] = [],
): { roots: ExplorerNode[]; filePathKeys: Map<string, string[]> } {
  const roots: ExplorerNode[] = [];
  const filePathKeys = new Map<string, string[]>();
  const filesByCategory = new Map<string, QaKnowledgeFile[]>();
  const documentFiles: QaKnowledgeFile[] = [];

  files.forEach((file) => {
    if (!file.topic_id) {
      documentFiles.push(file);
      return;
    }

    const categoryId = categoryPrefix(file.topic_id);
    const group = filesByCategory.get(categoryId) || [];
    group.push(file);
    filesByCategory.set(categoryId, group);
  });

  // Categories and topics are ordered by their stored `order` (set via
  // drag-to-reorder); fall back to label sort only when `order` is absent.
  const LARGE_ORDER = Number.MAX_SAFE_INTEGER;
  const categoryOrder = (id: string): number =>
    categories.find((item) => item.id === id)?.order ?? LARGE_ORDER;

  const sortedCategoryEntries = [...filesByCategory.entries()].sort(([leftId, leftFiles], [rightId, rightFiles]) => {
    if (!leftId && rightId) return 1;
    if (leftId && !rightId) return -1;
    const orderDelta = categoryOrder(leftId) - categoryOrder(rightId);
    if (orderDelta !== 0) return orderDelta;
    const leftCategory = categories.find((item) => item.id === leftId);
    const rightCategory = categories.find((item) => item.id === rightId);
    const leftLabel = leftCategory?.label || leftFiles[0]?.category_label || leftId;
    const rightLabel = rightCategory?.label || rightFiles[0]?.category_label || rightId;
    return sortByLabel(leftLabel, rightLabel);
  });

  sortedCategoryEntries.forEach(([categoryId, categoryFiles]) => {
    const category = categories.find((item) => item.id === categoryId);
    const categoryLabel =
      category?.label || categoryFiles[0]?.category_label || categoryId;
    const categoryKey = `category:${categoryId}`;
    const filesByTopic = new Map<string, QaKnowledgeFile[]>();

    categoryFiles.forEach((file) => {
      const topicKey = file.topic_id || NO_TOPIC_KEY;
      const group = filesByTopic.get(topicKey) || [];
      group.push(file);
      filesByTopic.set(topicKey, group);
    });

    const resolveTopicLabel = (topicId: string, topicFiles: QaKnowledgeFile[]): string => {
      if (topicId === NO_TOPIC_KEY) return getNoTopicLabel(language);
      return category?.topics.find((item) => item.id === topicId)?.label
        || topicFiles[0]?.topic_label
        || topicId;
    };

    const topicOrder = (topicId: string): number =>
      category?.topics.find((item) => item.id === topicId)?.order ?? LARGE_ORDER;

    const sortedTopicEntries = [...filesByTopic.entries()].sort(([leftId, leftFiles], [rightId, rightFiles]) => {
      const orderDelta = topicOrder(leftId) - topicOrder(rightId);
      if (orderDelta !== 0) return orderDelta;
      return sortByLabel(resolveTopicLabel(leftId, leftFiles), resolveTopicLabel(rightId, rightFiles));
    });

    const topicNodes: ExplorerNode[] = sortedTopicEntries.map(([topicId, topicFiles]) => {
      const topicLabel = resolveTopicLabel(topicId, topicFiles);
      const topicKey = `topic:${topicId}`;

      const csvFiles: QaKnowledgeFile[] = [];
      const nonCsvFiles: QaKnowledgeFile[] = [];
      topicFiles.forEach((file) => {
        if (isCsvFile(file)) {
          csvFiles.push(file);
        } else {
          nonCsvFiles.push(file);
        }
      });

      const childNodes: ExplorerNode[] = [];

      if (csvFiles.length > 0 && topicId !== NO_TOPIC_KEY) {
        childNodes.push({
          key: `merged-csv:${topicId}`,
          kind: 'merged-csv',
          label: 'Q&A 整合',
          topicId,
          csvCount: csvFiles.length,
        } satisfies ExplorerMergedCsvNode);
        csvFiles.forEach((file) => {
          filePathKeys.set(file.name, [categoryKey, topicKey]);
        });
      } else {
        sortFilesByDisplayLabel(csvFiles).forEach((file) => {
          appendFileNode(childNodes, filePathKeys, file, [categoryKey, topicKey]);
        });
      }

      sortFilesByDisplayLabel(nonCsvFiles).forEach((file) => {
        appendFileNode(childNodes, filePathKeys, file, [categoryKey, topicKey]);
      });

      if (childNodes.length === 1 && childNodes[0].kind === 'merged-csv') {
        return {
          ...(childNodes[0] as ExplorerMergedCsvNode),
          label: topicLabel,
        } satisfies ExplorerMergedCsvNode;
      }

      return {
        key: topicKey,
        kind: 'folder',
        label: topicLabel,
        tone: 'topic',
        topicId: topicId === NO_TOPIC_KEY ? undefined : topicId,
        children: childNodes,
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

  if (documentFiles.length > 0) {
    const docNodes: ExplorerNode[] = [];
    sortFilesByDisplayLabel(documentFiles).forEach((file) => {
      appendFileNode(docNodes, filePathKeys, file, [DOCUMENT_CATEGORY_KEY]);
    });

    roots.push({
      key: DOCUMENT_CATEGORY_KEY,
      kind: 'folder',
      label: '文件',
      tone: 'category',
      children: docNodes,
    });
  }

  if (images.length > 0) {
    const imageNodes: ExplorerNode[] = images
      .slice()
      .sort((left, right) => sortByLabel(left.image_id, right.image_id))
      .map((image) => ({
        key: `image:${image.image_id}`,
        kind: 'image',
        label: image.image_id,
        image,
      }));

    roots.push({
      key: 'category:__images__',
      kind: 'folder',
      label: '圖片',
      tone: 'category',
      children: imageNodes,
    });
  }

  return { roots, filePathKeys };
}
