import type { CSSProperties } from 'react';
import {
  ChevronDown,
  ChevronRight,
  FileText,
  Folder,
  FolderOpen,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Search,
} from 'lucide-react';

import type { HciotLanguage } from '../../../config/hciotTopics';
import type { ExplorerRow } from './shared';
import { isFolderNode } from './shared';

interface ExplorerSidebarProps {
  language: HciotLanguage;
  sidebarCollapsed: boolean;
  loadingWorkspace: boolean;
  searchQuery: string;
  deferredSearchQuery: string;
  selectedFileName: string | null;
  visibleRows: ExplorerRow[];
  visibleExpandedKeys: Set<string>;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
  onToggleSidebar: () => void;
  onSearchChange: (value: string) => void;
  onToggleExpanded: (key: string) => void;
  onSelectFile: (fileName: string) => void;
  onOpenUploadDialog: () => void;
}

export default function ExplorerSidebar({
  language,
  sidebarCollapsed,
  loadingWorkspace,
  searchQuery,
  deferredSearchQuery,
  selectedFileName,
  visibleRows,
  visibleExpandedKeys,
  onMouseEnter,
  onMouseLeave,
  onToggleSidebar,
  onSearchChange,
  onToggleExpanded,
  onSelectFile,
  onOpenUploadDialog,
}: ExplorerSidebarProps) {
  return (
    <aside
      className={`hciot-explorer${sidebarCollapsed ? ' is-collapsed' : ''}`}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div className="hciot-explorer-toolbar">
        <button
          type="button"
          className="hciot-explorer-icon-button"
          onClick={onToggleSidebar}
          title={sidebarCollapsed
            ? (language === 'zh' ? '展開側欄' : 'Expand sidebar')
            : (language === 'zh' ? '收合側欄' : 'Collapse sidebar')}
        >
          {sidebarCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </button>

        <div className="hciot-explorer-search">
          <Search size={15} />
          <input
            type="search"
            value={searchQuery}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder={language === 'zh' ? '搜尋檔案樹' : 'Filter explorer'}
          />
        </div>

        <button
          type="button"
          className="hciot-explorer-icon-button"
          onClick={onOpenUploadDialog}
          title={language === 'zh' ? '新增知識' : 'Add knowledge'}
        >
          <Plus size={16} />
        </button>
      </div>

      <div className="hciot-explorer-body">
        {loadingWorkspace ? (
          <div className="hciot-explorer-empty">{language === 'zh' ? '載入中...' : 'Loading...'}</div>
        ) : visibleRows.length > 0 ? (
          <div className="hciot-explorer-tree" role="tree">
            {visibleRows.map(({ node, depth }) => {
              const isSelected = node.kind === 'file' && node.file.name === selectedFileName;
              const isExpanded = isFolderNode(node) && (
                Boolean(deferredSearchQuery) || visibleExpandedKeys.has(node.key)
              );

              return (
                <button
                  key={node.key}
                  type="button"
                  className={`hciot-explorer-row${isSelected ? ' is-selected' : ''}`}
                  style={{ '--row-depth': depth } as CSSProperties}
                  onClick={() => {
                    if (node.kind === 'file') {
                      onSelectFile(node.file.name);
                      return;
                    }
                    onToggleExpanded(node.key);
                  }}
                  role="treeitem"
                  aria-expanded={isFolderNode(node) ? isExpanded : undefined}
                >
                  <span className="hciot-explorer-row-indent" />
                  <span className="hciot-explorer-row-caret">
                    {isFolderNode(node) ? (
                      isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />
                    ) : null}
                  </span>
                  <span className={`hciot-explorer-row-icon tone-${isFolderNode(node) ? node.tone || 'category' : 'file'}`}>
                    {isFolderNode(node)
                      ? (isExpanded ? <FolderOpen size={15} /> : <Folder size={15} />)
                      : <FileText size={15} />}
                  </span>
                  <span className="hciot-explorer-row-label">{node.label}</span>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="hciot-explorer-empty">
            {searchQuery
              ? (language === 'zh' ? '找不到符合的節點' : 'No matching nodes')
              : (language === 'zh' ? '目前沒有知識檔案' : 'No knowledge files yet')}
          </div>
        )}
      </div>
    </aside>
  );
}
