import { type CSSProperties, useEffect, useState } from 'react';
import {
  Check,
  ChevronDown,
  ChevronRight,
  FileText,
  Folder,
  FolderOpen,
  GripVertical,
  Pencil,
  Plus,
  Search,
  Trash2,
  X,
  Image as ImageIcon,
  Table as TableIcon,
  RefreshCw,
} from 'lucide-react';
import {
  DndContext,
  type DragEndEvent,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import { SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

import type { ExplorerNode, ExplorerRow } from './explorerTree';
import { isFolderNode } from './explorerTree';

const IMAGES_CATEGORY_KEY = 'category:__images__';

function getEditableNodeKey(node: ExplorerNode): string | null {
  if (!isFolderNode(node)) {
    return node.kind === 'merged-csv' ? `topic:${node.topicId}` : null;
  }
  if (node.tone === 'category') {
    return node.key === IMAGES_CATEGORY_KEY ? null : node.key;
  }
  if (node.tone === 'topic') {
    return node.topicId ? node.key : null;
  }
  return null;
}

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
  onReindex?: () => void;
  reindexing?: boolean;
  renamingKey: string | null;
  renaming: boolean;
  onStartRename: (key: string) => void;
  onCommitRename: (key: string, nextLabel: string) => void;
  onCancelRename: () => void;
  // Called when a category/topic row is dropped onto another. Keys are node
  // keys ("category:<id>" / "topic:<id>"). The workspace recomputes ordering.
  onReorder: (activeKey: string, overKey: string) => void;
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
  onReindex,
  reindexing,
  renamingKey,
  renaming,
  onStartRename,
  onCommitRename,
  onCancelRename,
  onReorder,
}: ExplorerSidebarProps) {
  // Require a small drag distance so a plain click still selects/expands.
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) {
      return;
    }
    onReorder(String(active.id), String(over.id));
  };

  const sortableKeys = visibleRows
    .map(({ node }) => getEditableNodeKey(node))
    .filter((id): id is string => id !== null);

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

          {onReindex && (
            <button
              type="button"
              className={`hciot-explorer-icon-button reindex${reindexing ? ' is-loading' : ''}`}
              onClick={onReindex}
              disabled={reindexing}
              title="重新索引 RAG (暫停約 1 分鐘)"
              aria-label="重新索引 RAG"
            >
              <RefreshCw size={16} className={reindexing ? 'animate-spin' : ''} />
            </button>
          )}

        </div>
      </div>

      <div className="hciot-explorer-body">
        {loadingWorkspace ? (
          <div className="hciot-explorer-empty">載入中...</div>
        ) : visibleRows.length > 0 ? (
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
            <SortableContext items={sortableKeys} strategy={verticalListSortingStrategy}>
              <div className="hciot-explorer-tree" role="tree">
                {visibleRows.map(({ node, depth }) => {
                  const isExpanded = isFolderNode(node) && (
                    Boolean(deferredSearchQuery) || visibleExpandedKeys.has(node.key)
                  );
                  const nodeKey = getEditableNodeKey(node);

                  if (nodeKey !== null && renamingKey === nodeKey) {
                    return (
                      <div
                        key={node.key}
                        className="hciot-explorer-row-wrap is-renaming"
                        style={{ '--row-depth': depth } as CSSProperties}
                      >
                        <RenameRow
                          initialLabel={node.label}
                          saving={renaming}
                          onCommit={(value) => onCommitRename(nodeKey, value)}
                          onCancel={onCancelRename}
                        />
                      </div>
                    );
                  }

                  return (
                    <ExplorerRowItem
                      key={node.key}
                      node={node}
                      nodeKey={nodeKey}
                      depth={depth}
                      isExpanded={isExpanded}
                      selectedFileName={selectedFileName}
                      selectedImageName={selectedImageName}
                      selectedMergedTopicId={selectedMergedTopicId}
                      renaming={renaming}
                      onSelectFile={onSelectFile}
                      onSelectImage={onSelectImage}
                      onSelectMergedCsv={onSelectMergedCsv}
                      onToggleExpanded={onToggleExpanded}
                      onStartRename={onStartRename}
                      onDeleteTopic={onDeleteTopic}
                    />
                  );
                })}
              </div>
            </SortableContext>
          </DndContext>
        ) : (
          <div className="hciot-explorer-empty">
            {searchQuery ? '找不到符合的節點' : '目前沒有知識檔案'}
          </div>
        )}
      </div>
    </aside>
  );
}

interface ExplorerRowItemProps {
  node: ExplorerNode;
  nodeKey: string | null;
  depth: number;
  isExpanded: boolean;
  selectedFileName: string | null;
  selectedImageName: string | null;
  selectedMergedTopicId: string | null;
  renaming: boolean;
  onSelectFile: (fileName: string) => void;
  onSelectImage: (fileName: string) => void;
  onSelectMergedCsv: (topicId: string) => void;
  onToggleExpanded: (key: string) => void;
  onStartRename: (key: string) => void;
  onDeleteTopic?: (topicId: string, topicLabel: string) => void;
}

/** A single explorer tree row. Category/topic folders are drag-sortable. */
function ExplorerRowItem({
  node,
  nodeKey,
  depth,
  isExpanded,
  selectedFileName,
  selectedImageName,
  selectedMergedTopicId,
  renaming,
  onSelectFile,
  onSelectImage,
  onSelectMergedCsv,
  onToggleExpanded,
  onStartRename,
  onDeleteTopic,
}: ExplorerRowItemProps) {
  // useSortable is always called (hooks rule); when the node is not reorderable
  // we simply ignore its drag handles.
  const sortable = useSortable({ id: nodeKey ?? node.key, disabled: nodeKey === null });

  const isSelected =
    (node.kind === 'file' && node.file.name === selectedFileName) ||
    (node.kind === 'image' && node.image.image_id === selectedImageName) ||
    (node.kind === 'merged-csv' && node.topicId === selectedMergedTopicId);

  const deletableTopicId = getDeletableTopicId(node);
  const nodeIconTone = getNodeIconTone(node);
  const rowClassName = `hciot-explorer-row-wrap${isSelected ? ' is-selected' : ''}${sortable.isDragging ? ' is-dragging' : ''}`;

  const style: CSSProperties = {
    '--row-depth': depth,
    transform: CSS.Transform.toString(sortable.transform),
    transition: sortable.transition,
  } as CSSProperties;

  return (
    <div
      ref={sortable.setNodeRef}
      className={rowClassName}
      style={style}
    >
      {nodeKey && (
        <button
          type="button"
          className="hciot-explorer-row-grip"
          title="拖曳排序"
          aria-label="拖曳排序"
          {...sortable.attributes}
          {...sortable.listeners}
        >
          <GripVertical size={13} />
        </button>
      )}
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
      {nodeKey && !renaming && (
        <button
          type="button"
          className="hciot-explorer-row-rename"
          title="重新命名"
          onClick={(e) => {
            e.stopPropagation();
            onStartRename(nodeKey);
          }}
        >
          <Pencil size={12} />
        </button>
      )}
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
}

interface RenameRowProps {
  initialLabel: string;
  saving: boolean;
  onCommit: (nextLabel: string) => void;
  onCancel: () => void;
}

function RenameRow({ initialLabel, saving, onCommit, onCancel }: RenameRowProps) {
  const [value, setValue] = useState(initialLabel);

  useEffect(() => {
    setValue(initialLabel);
  }, [initialLabel]);

  const commit = () => {
    const nextLabel = value.trim();
    if (!nextLabel || nextLabel === initialLabel) {
      onCancel();
      return;
    }
    onCommit(nextLabel);
  };

  return (
    <div className="hciot-explorer-rename">
      <input
        type="text"
        className="hciot-explorer-rename-input"
        value={value}
        autoFocus
        disabled={saving}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            commit();
          } else if (event.key === 'Escape') {
            event.preventDefault();
            onCancel();
          }
        }}
      />
      <button
        type="button"
        className="hciot-explorer-rename-confirm"
        title="儲存"
        disabled={saving}
        onClick={commit}
      >
        <Check size={13} />
      </button>
      <button
        type="button"
        className="hciot-explorer-rename-cancel"
        title="取消"
        disabled={saving}
        onClick={onCancel}
      >
        <X size={13} />
      </button>
    </div>
  );
}
