import type { HciotLanguage } from '../../../../config/hciotTopics';
import type { HciotImage, HciotKnowledgeFile, HciotTopicCategory } from '../../../../services/api/hciot';
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
  file: HciotKnowledgeFile;
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
  image: HciotImage;
}

export type ExplorerNode = ExplorerFolderNode | ExplorerFileNode | ExplorerImageNode | ExplorerMergedCsvNode;

export interface ExplorerRow {
  node: ExplorerNode;
  depth: number;
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

export function getNoTopicLabel(_language: HciotLanguage): string {
  return '未指定主題';
}

export function getCurrentPathLabel(
  selectedFile: HciotKnowledgeFile | null,
  language: HciotLanguage,
): string {
  if (!selectedFile) {
    return '選擇檔案開始編輯';
  }

  const categoryLabel = selectedFile[`category_label_${language}` as const] || categoryPrefix(selectedFile.topic_id);
  const topicLabel = selectedFile[`topic_label_${language}` as const] || selectedFile.topic_id;
  if (!categoryLabel && !topicLabel) {
    return '未分類';
  }

  return topicLabel ? `${categoryLabel} / ${topicLabel}` : categoryLabel;
}

export function buildExplorerTree(
  files: HciotKnowledgeFile[],
  categories: HciotTopicCategory[],
  language: HciotLanguage,
  images: HciotImage[] = [],
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
    if (!leftId && rightId) return 1;
    if (leftId && !rightId) return -1;
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

    const resolveTopicLabel = (topicId: string, topicFiles: HciotKnowledgeFile[]): string => {
      if (topicId === NO_TOPIC_KEY) return getNoTopicLabel(language);
      return category?.topics.find((item) => item.id === topicId)?.labels[language]
        || topicFiles[0]?.[`topic_label_${language}` as const]
        || topicId;
    };

    const sortedTopicEntries = [...filesByTopic.entries()].sort(([leftId, leftFiles], [rightId, rightFiles]) => {
      return sortByLabel(resolveTopicLabel(leftId, leftFiles), resolveTopicLabel(rightId, rightFiles));
    });

    const topicNodes: ExplorerNode[] = sortedTopicEntries.map(([topicId, topicFiles]) => {
      const topicLabel = resolveTopicLabel(topicId, topicFiles);
      const topicKey = `topic:${topicId}`;

      const csvFiles = topicFiles.filter((f) => (f.name || '').toLowerCase().endsWith('.csv'));
      const nonCsvFiles = topicFiles.filter((f) => !(f.name || '').toLowerCase().endsWith('.csv'));

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
        csvFiles
          .slice()
          .sort((left, right) => sortByLabel(getFileLabel(left), getFileLabel(right)))
          .forEach((file) => {
            filePathKeys.set(file.name, [categoryKey, topicKey]);
            childNodes.push({
              key: `file:${file.name}`,
              kind: 'file',
              label: getFileLabel(file),
              file,
            } satisfies ExplorerFileNode);
          });
      }

      nonCsvFiles
        .slice()
        .sort((left, right) => sortByLabel(getFileLabel(left), getFileLabel(right)))
        .forEach((file) => {
          filePathKeys.set(file.name, [categoryKey, topicKey]);
          childNodes.push({
            key: `file:${file.name}`,
            kind: 'file',
            label: getFileLabel(file),
            file,
          } satisfies ExplorerFileNode);
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

  if (images.length > 0) {
    const imageNodes: ExplorerNode[] = images
      .slice()
      .sort((a, b) => sortByLabel(a.image_id, b.image_id))
      .map((img) => ({
        key: `image:${img.image_id}`,
        kind: 'image',
        label: img.image_id,
        image: img,
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
