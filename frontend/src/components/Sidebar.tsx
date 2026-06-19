import { useRef, useState } from 'react';
import { ChevronRight, FileText, Plus, Trash2 } from 'lucide-react';
import type { FileItem, KnowledgeTarget, Store } from '../types';
import { PROJECT_COLORS, getStoreIcon, isManagedKnowledgeStore } from '../utils/storeDisplay';

interface SidebarProps {
  isOpen: boolean;
  stores: Store[];
  keyNames: string[];
  knowledgeTargets: KnowledgeTarget[];
  currentTargetId: string | null;
  files: FileItem[];
  filesLoading: boolean;
  onTargetChange: (targetId: string) => void;
  onUploadFile: (file: File) => Promise<void>;
  onDeleteFile: (fileName: string) => void;
  onCreateStore: (name: string, keyIndex: number) => Promise<void>;
  onOpenFile?: (file: FileItem) => void;
  canManageKnowledge?: boolean;
  onOpenKnowledgeWorkspace?: () => void;
}

interface ProjectGroup {
  index: number;
  name: string;
  color: string;
  stores: Store[];
}

function buildProjectGroups(stores: Store[], keyNames: string[]): ProjectGroup[] {
  const effectiveKeyNames = keyNames.length > 0 ? keyNames : ['全部專案'];
  const groups = effectiveKeyNames.map((name, index) => ({
    index,
    name: name || `Key #${index + 1}`,
    color: PROJECT_COLORS[index % PROJECT_COLORS.length],
    stores: stores.filter(
      (store) => (typeof store.key_index === 'number' ? store.key_index : 0) === index,
    ),
  }));

  const assignedIndexes = new Set(groups.map((group) => group.index));
  const orphanStores = stores.filter(
    (store) => typeof store.key_index !== 'number' || !assignedIndexes.has(store.key_index),
  );
  if (orphanStores.length > 0) {
    groups[0].stores.push(...orphanStores);
  }

  return groups;
}

export default function Sidebar({
  isOpen,
  stores,
  keyNames,
  knowledgeTargets,
  currentTargetId,
  files,
  filesLoading,
  onTargetChange,
  onUploadFile,
  onDeleteFile,
  onCreateStore,
  onOpenKnowledgeWorkspace,
  onOpenFile,
  canManageKnowledge = true,
}: SidebarProps) {
  const [collapsedProjects, setCollapsedProjects] = useState<Record<string, boolean>>({});
  const [creatingForKey, setCreatingForKey] = useState<number | null>(null);
  const [newStoreName, setNewStoreName] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const activeTarget = knowledgeTargets.find((t) => t.id === currentTargetId);
  const activeStore = activeTarget?.kind === 'store'
    ? stores.find((store) => store.name === activeTarget.storeName)
    : null;

  const toggleProject = (key: string) =>
    setCollapsedProjects((p) => ({ ...p, [key]: !p[key] }));

  const projectGroups = buildProjectGroups(stores, keyNames);

  const handleCreateStore = async () => {
    if (!newStoreName.trim() || creatingForKey === null) return;
    await onCreateStore(newStoreName.trim(), creatingForKey);
    setNewStoreName('');
    setCreatingForKey(null);
  };

  const beginCreate = (keyIndex: number) => {
    setCreatingForKey(keyIndex);
    setNewStoreName('');
    setCollapsedProjects((p) => ({ ...p, [String(keyIndex)]: false }));
  };

  const cancelCreate = () => {
    setCreatingForKey(null);
    setNewStoreName('');
  };

  /* ── File upload ── */
  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      await onUploadFile(file);
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (uploading) return;
    const file = e.dataTransfer.files[0];
    if (file) await handleUpload(file);
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      await handleUpload(file);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  return (
    <aside className={`sidebar${isOpen ? '' : ' closed'}`} aria-label="側邊欄">
      <div className="sb-header">
        <span className="sb-title">知識庫</span>
      </div>

      <div className="sb-body">
        {projectGroups.map((group) => {
          const isOpen = !collapsedProjects[String(group.index)];
          return (
            <div key={group.index} className="project-group">
              <div
                className="project-header"
                onClick={() => toggleProject(String(group.index))}
              >
                <div className="project-dot" style={{ background: group.color }} />
                <span className="project-name">{group.name}</span>
                {canManageKnowledge && (
                  <button
                    className="project-add"
                    title={`在 ${group.name} 建立知識庫`}
                    onClick={(e) => {
                      e.stopPropagation();
                      beginCreate(group.index);
                    }}
                  >
                    <Plus size={12} />
                  </button>
                )}
                <span className={`project-chevron${isOpen ? ' open' : ''}`}>
                  <ChevronRight size={13} />
                </span>
              </div>
              {isOpen && (
                <ul className="store-list">
                  {group.stores.length === 0 && creatingForKey !== group.index && (
                    <li className="store-empty">尚無知識庫</li>
                  )}
                  {canManageKnowledge && creatingForKey === group.index && (
                    <li className="store-create-row">
                      <input
                        className="store-create-input"
                        placeholder="知識庫名稱..."
                        value={newStoreName}
                        autoFocus
                        onChange={(e) => setNewStoreName(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') void handleCreateStore();
                          if (e.key === 'Escape') cancelCreate();
                        }}
                      />
                      <div className="store-create-actions">
                        <button className="btn btn-ghost btn-sm" onClick={cancelCreate}>
                          取消
                        </button>
                        <button
                          className="btn btn-primary btn-sm"
                          onClick={handleCreateStore}
                          disabled={!newStoreName.trim()}
                        >
                          建立
                        </button>
                      </div>
                    </li>
                  )}
                  {group.stores.map((store) => {
                    const target = knowledgeTargets.find(
                      (t) => t.kind === 'store' && t.storeName === store.name,
                    );
                    const isActive = target?.id === currentTargetId;
                    const isFixedStore = isManagedKnowledgeStore(store);
                    return (
                      <li key={store.name}>
                        <button
                          className={`store-item-btn${isActive ? ' active' : ''}`}
                          onClick={() => target && onTargetChange(target.id)}
                        >
                          <div className="si-icon">{getStoreIcon(store.managed_app || '')}</div>
                          <div className="si-text">
                            <div className="si-name">
                              {store.display_name || store.name}
                            </div>
                            <div className="si-meta">
                              {isFixedStore
                                ? '固定知識庫'
                                : `${store.file_count ?? 0} 個檔案`}
                            </div>
                          </div>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          );
        })}
      </div>

      {/* File panel for active store */}
      {activeStore && (
        <div className="file-panel">
          <div className="fp-header">
            <span className="fp-title">文件</span>
            {canManageKnowledge && (
              <button
                className="icon-btn icon-btn-sm"
                title="上傳"
                onClick={() => fileInputRef.current?.click()}
              >
                <Plus size={14} />
              </button>
            )}
          </div>
          <ul className="file-list-inner">
            {filesLoading ? (
              <li className="fp-empty">
                載入中...
              </li>
            ) : files.length === 0 ? (
              <li className="fp-empty">
                尚無文件
              </li>
            ) : (
              files.map((f) => (
                <li key={f.name} className="file-row">
                  <button
                    className="file-row-main"
                    onClick={() => onOpenFile?.(f)}
                    title={`預覽 ${f.display_name || f.name}`}
                  >
                    <FileText size={13} />
                    <span className="file-name">
                      {f.display_name || f.name}
                    </span>
                  </button>
                  {canManageKnowledge && !isManagedKnowledgeStore(activeStore) && (
                    <button
                      className="file-del"
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteFile(f.name);
                      }}
                      title="刪除"
                    >
                      <Trash2 size={13} />
                    </button>
                  )}
                </li>
              ))
            )}
          </ul>
          {canManageKnowledge && !isManagedKnowledgeStore(activeStore) && (
            <div
              className="drop-zone"
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              style={dragOver ? { borderColor: 'var(--primary)', background: 'var(--primary-lt)' } : undefined}
            >
              {uploading ? '上傳中...' : (<>拖曳或<span>選擇</span>上傳</>)}
            </div>
          )}
          {canManageKnowledge && !isManagedKnowledgeStore(activeStore) && onOpenKnowledgeWorkspace && (
            <button
              type="button"
              className="knowledge-workspace-btn"
              onClick={onOpenKnowledgeWorkspace}
            >
              管理知識庫工作區
            </button>
          )}
          {canManageKnowledge && (
            <input className="file-input-hidden" ref={fileInputRef} type="file" onChange={handleFileSelect} aria-label="選擇文件" />
          )}
        </div>
      )}

    </aside>
  );
}
