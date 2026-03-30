import type { CSSProperties, RefObject } from 'react';
import {
  ChevronDown,
  ChevronRight,
  FileText,
  Folder,
  FolderOpen,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Upload,
} from 'lucide-react';

import type { HciotLanguage } from '../../../config/hciotTopics';
import type { ExplorerRow } from './shared';
import { isFolderNode } from './shared';

interface ExplorerSidebarProps {
  language: HciotLanguage;
  sidebarCollapsed: boolean;
  loadingWorkspace: boolean;
  uploading: boolean;
  searchQuery: string;
  deferredSearchQuery: string;
  selectedFileName: string | null;
  visibleRows: ExplorerRow[];
  visibleExpandedKeys: Set<string>;
  fileInputRef: RefObject<HTMLInputElement | null>;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
  onToggleSidebar: () => void;
  onSearchChange: (value: string) => void;
  onUploadFiles: (files: FileList | null) => void;
  onToggleExpanded: (key: string) => void;
  onSelectFile: (fileName: string) => void;
}

export default function ExplorerSidebar({
  language,
  sidebarCollapsed,
  loadingWorkspace,
  uploading,
  searchQuery,
  deferredSearchQuery,
  selectedFileName,
  visibleRows,
  visibleExpandedKeys,
  fileInputRef,
  onMouseEnter,
  onMouseLeave,
  onToggleSidebar,
  onSearchChange,
  onUploadFiles,
  onToggleExpanded,
  onSelectFile,
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
          onClick={() => fileInputRef.current?.click()}
          title={language === 'zh' ? '上傳檔案' : 'Upload files'}
          disabled={uploading}
        >
          <Upload size={16} />
        </button>

        <input
          ref={fileInputRef}
          type="file"
          hidden
          multiple
          onChange={(event) => onUploadFiles(event.target.files)}
        />
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
