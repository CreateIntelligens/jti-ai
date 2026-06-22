import { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';
import type { QaLanguage, QaAdminCategory } from '../../../../config/qaTopics';
import type {
  QaImage,
  QaKnowledgeFile,
} from '../../../../services/api/_shared/qaKnowledge';
import {
  buildExplorerTree,
  filterExplorerNodes,
  flattenExplorerNodes,
  readExpandedKeys,
  writeExpandedKeys,
} from '../explorer/explorerTree';

export interface UseExplorerTreeOptions {
  files: QaKnowledgeFile[];
  categories: QaAdminCategory[];
  language: QaLanguage;
  images: QaImage[];
}

export function useExplorerTree({
  files,
  categories,
  language,
  images,
}: UseExplorerTreeOptions) {
  const suppressHoverRef = useRef(false);

  const [expandedKeys, setExpandedKeys] = useState<string[]>(() => readExpandedKeys(language));
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarHoverExpanded, setSidebarHoverExpanded] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const deferredSearchQuery = useDeferredValue(searchQuery.trim().toLowerCase());

  useEffect(() => {
    setExpandedKeys(readExpandedKeys(language));
  }, [language]);

  useEffect(() => {
    writeExpandedKeys(language, expandedKeys);
  }, [expandedKeys, language]);

  const { roots, filePathKeys } = useMemo(
    () => buildExplorerTree(files, categories, language, images),
    [categories, files, language, images],
  );

  const filteredRoots = useMemo(
    () => filterExplorerNodes(roots, deferredSearchQuery),
    [deferredSearchQuery, roots],
  );

  const visibleExpandedKeys = useMemo(() => new Set(expandedKeys), [expandedKeys]);

  const visibleRows = useMemo(
    () => flattenExplorerNodes(filteredRoots, visibleExpandedKeys, deferredSearchQuery),
    [deferredSearchQuery, filteredRoots, visibleExpandedKeys],
  );

  const toggleExpanded = (key: string) => {
    setExpandedKeys((previous) => {
      if (previous.includes(key)) {
        return previous.filter((item) => item !== key);
      }
      return [...previous, key];
    });
  };

  const ensureSelectedPathExpanded = (fileName: string) => {
    const ancestorKeys = filePathKeys.get(fileName) || [];
    if (!ancestorKeys.length) return;

    setExpandedKeys((previous) => {
      const nextKeys = new Set(previous);
      ancestorKeys.forEach((key) => nextKeys.add(key));
      return [...nextKeys];
    });
  };

  const handleSidebarMouseEnter = () => {
    if (sidebarCollapsed && !suppressHoverRef.current) {
      setSidebarHoverExpanded(true);
    }
  };

  const handleSidebarMouseLeave = () => {
    if (sidebarCollapsed) {
      setSidebarHoverExpanded(false);
    }
  };

  const handleToggleSidebar = () => {
    const willCollapse = !sidebarCollapsed;
    setSidebarCollapsed(willCollapse);
    setSidebarHoverExpanded(false);

    if (willCollapse) {
      suppressHoverRef.current = true;
      window.setTimeout(() => {
        suppressHoverRef.current = false;
      }, 300);
    }
  };

  return {
    expandedKeys,
    setExpandedKeys,
    sidebarCollapsed,
    setSidebarCollapsed,
    sidebarHoverExpanded,
    searchQuery,
    setSearchQuery,
    deferredSearchQuery,
    roots,
    filePathKeys,
    filteredRoots,
    visibleExpandedKeys,
    visibleRows,
    toggleExpanded,
    ensureSelectedPathExpanded,
    handleSidebarMouseEnter,
    handleSidebarMouseLeave,
    handleToggleSidebar,
    suppressHoverRef,
  };
}
