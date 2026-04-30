import { type CSSProperties } from 'react';
import {
  ChevronDown,
  ChevronRight,
  FileText,
  Folder,
  FolderOpen,
  Plus,
  Search,
  Trash2,
  Image as ImageIcon,
  Table as TableIcon,
} from 'lucide-react';

import type { ExplorerNode, ExplorerRow } from './explorerTree';
import { isFolderNode } from './explorerTree';

interface ExplorerSidebarProps {
  sidebarCollapsed: boolean;
  loadingWorkspace: boolean;
  searchQuery: string;
  deferredSearchQuery: string;
  selectedFileName: string | null;
  selectedImageName: string | null;
  visibleRows: ExplorerRow[];
  visibleExpandedKeys: Set<string>;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
  onToggleSidebar: () => void;
  onSearchChange: (value: string) => void;
  onToggleExpanded: (key: string) => void;
  selectedMergedTopicId: string | null;
  onSelectFile: (fileName: string) => void;
  onSelectImage: (fileName: string) => void;
  onSelectMergedCsv: (topicId: string) => void;
  onOpenUploadDialog: () => void;
  onDeleteTopic?: (topicId: string, topicLabel: string) => void;
}

function getDeletableTopicId(node: ExplorerNode): string | null {
  if (isFolderNode(node)) {
    return node.tone === 'topic' && node.topicId ? node.topicId : null;
  }

  return node.kind === 'merged-csv' ? node.topicId : null;
}

function getNodeIconTone(node: ExplorerNode): string {
  if (isFolderNode(node)) {
    return node.tone || 'category';
  }

  if (node.kind === 'merged-csv') {
    return 'merged';
  }

  return 'file';
}

function renderNodeIcon(node: ExplorerNode, isExpanded: boolean) {
  if (isFolderNode(node)) {
    return isExpanded ? <FolderOpen size={15} /> : <Folder size={15} />;
  }

  if (node.kind === 'merged-csv') {
    return <TableIcon size={15} />;
  }

  if (node.kind === 'image') {
    return <ImageIcon size={15} />;
  }

  return <FileText size={15} />;
}

export default function ExplorerSidebar({
  sidebarCollapsed,
  loadingWorkspace,
  searchQuery,
  deferredSearchQuery,
  selectedFileName,
  selectedImageName,
  visibleRows,
  visibleExpandedKeys,
  onMouseEnter,
  onMouseLeave,
  onSearchChange,
  onToggleExpanded,
  selectedMergedTopicId,
  onSelectFile,
  onSelectImage,
  onSelectMergedCsv,
  onOpenUploadDialog,
  onDeleteTopic,
}: ExplorerSidebarProps) {
  return (
    <aside
      className={`hciot-explorer${sidebarCollapsed ? ' is-collapsed' : ''}`}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div className="hciot-explorer-toolbar">
        <div className="hciot-explorer-search">
          <Search size={15} />
          <input
            type="search"
            value={searchQuery}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="搜尋檔案樹"
          />
        </div>

        <div className="hciot-explorer-actions">
          <button
            type="button"
            className="hciot-explorer-icon-button"
            onClick={onOpenUploadDialog}
            title="新增內容"
            aria-label="新增內容"
          >
            <Plus size={16} />
          </button>

        </div>
      </div>

      <div className="hciot-explorer-body">
        {loadingWorkspace ? (
          <div className="hciot-explorer-empty">載入中...</div>
        ) : visibleRows.length > 0 ? (
          <div className="hciot-explorer-tree" role="tree">
            {visibleRows.map(({ node, depth }) => {
              const isSelected =
                (node.kind === 'file' && node.file.name === selectedFileName) ||
                (node.kind === 'image' && node.image.image_id === selectedImageName) ||
                (node.kind === 'merged-csv' && node.topicId === selectedMergedTopicId);
              const isExpanded = isFolderNode(node) && (
                Boolean(deferredSearchQuery) || visibleExpandedKeys.has(node.key)
              );

              const deletableTopicId = getDeletableTopicId(node);
              const nodeIconTone = getNodeIconTone(node);

              return (
                <div
                  key={node.key}
                  className={`hciot-explorer-row-wrap${isSelected ? ' is-selected' : ''}`}
                  style={{ '--row-depth': depth } as CSSProperties}
                >
                  <button
                    type="button"
                    className={`hciot-explorer-row${isSelected ? ' is-selected' : ''}`}
                    onClick={() => {
                      if (node.kind === 'file') {
                        onSelectFile(node.file.name);
                      } else if (node.kind === 'image') {
                        onSelectImage(node.image.image_id);
                      } else if (node.kind === 'merged-csv') {
                        onSelectMergedCsv(node.topicId);
                      } else {
                        onToggleExpanded(node.key);
                      }
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
                    <span className={`hciot-explorer-row-icon tone-${nodeIconTone}`}>
                      {renderNodeIcon(node, isExpanded)}
                    </span>
                    <span className="hciot-explorer-row-label">{node.label}</span>
                  </button>
                  {deletableTopicId && onDeleteTopic && (
                    <button
                      type="button"
                      className="hciot-explorer-row-delete"
                      title="刪除整個主題"
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteTopic(deletableTopicId, node.label);
                      }}
                    >
                      <Trash2 size={13} />
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="hciot-explorer-empty">
            {searchQuery ? '找不到符合的節點' : '目前沒有知識檔案'}
          </div>
        )}
      </div>
    </aside>
  );
}
