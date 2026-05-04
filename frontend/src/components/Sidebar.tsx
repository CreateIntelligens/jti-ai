import { useRef, useState } from 'react';
import { ChevronRight, FileText, Plus, Trash2 } from 'lucide-react';
import type { FileItem, KnowledgeTarget, Store } from '../types';
import { PROJECT_COLORS, getStoreIcon } from '../utils/storeDisplay';

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
}: SidebarProps) {
  const [collapsedProjects, setCollapsedProjects] = useState<Record<string, boolean>>({});
  const [creatingStore, setCreatingStore] = useState(false);
  const [newStoreName, setNewStoreName] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const activeTarget = knowledgeTargets.find((t) => t.id === currentTargetId);
  const activeStore = activeTarget?.kind === 'store' ? stores.find((s) => s.name === activeTarget.storeName) : null;

  const toggleProject = (key: string) =>
    setCollapsedProjects((p) => ({ ...p, [key]: !p[key] }));

  /* ── Group stores by key_index ── */
  const projectGroups: Array<{ index: number; name: string; color: string; stores: Store[] }> = [];
  const effectiveKeyNames = keyNames.length > 0 ? keyNames : ['全部專案'];
  effectiveKeyNames.forEach((name, i) => {
    const groupStores = stores.filter(
      (s) => (typeof s.key_index === 'number' ? s.key_index : 0) === i,
    );
    if (groupStores.length > 0 || effectiveKeyNames.length <= 1) {
      projectGroups.push({
        index: i,
        name: name || `Key #${i + 1}`,
        color: PROJECT_COLORS[i % PROJECT_COLORS.length],
        stores: groupStores,
      });
    }
  });
  // Catch stores with no key_index or out-of-range index
  const assignedIndexes = new Set(projectGroups.map((g) => g.index));
  const orphanStores = stores.filter(
    (s) => typeof s.key_index !== 'number' || !assignedIndexes.has(s.key_index),
  );
  if (orphanStores.length > 0 && projectGroups.length > 0) {
    projectGroups[0].stores.push(...orphanStores);
  } else if (orphanStores.length > 0) {
    projectGroups.push({
      index: 0,
      name: '全部專案',
      color: PROJECT_COLORS[0],
      stores: orphanStores,
    });
  }

  const handleCreateStore = async () => {
    if (!newStoreName.trim()) return;
    await onCreateStore(newStoreName.trim(), 0);
    setNewStoreName('');
    setCreatingStore(false);
  };

  /* ── File upload ── */
  const handleUpload = async (file: File) => {
    setUploading(true);
    try { await onUploadFile(file); }
    finally { setUploading(false); }
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
                <span className={`project-chevron${isOpen ? ' open' : ''}`}>
                  <ChevronRight size={13} />
                </span>
              </div>
              {isOpen && (
                <ul className="store-list">
                  {group.stores.map((store) => {
                    const target = knowledgeTargets.find(
                      (t) => t.kind === 'store' && t.storeName === store.name,
                    );
                    const isActive = target?.id === currentTargetId;
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
                              {store.managed_app
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
            <button className="icon-btn icon-btn-sm" title="上傳" onClick={() => fileInputRef.current?.click()}
            >
              <Plus size={14} />
            </button>
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
                  <FileText size={13} />
                  <span className="file-name" title={f.display_name || f.name}>
                    {f.display_name || f.name}
                  </span>
                  {!activeStore.managed_app && (
                    <button
                      className="file-del"
                      onClick={() => onDeleteFile(f.name)}
                      title="刪除"
                    >
                      <Trash2 size={13} />
                    </button>
                  )}
                </li>
              ))
            )}
          </ul>
          {!activeStore.managed_app && (
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
          <input className="file-input-hidden" ref={fileInputRef} type="file" onChange={handleFileSelect} aria-label="選擇文件" />
        </div>
      )}

      {/* Footer: new store */}
      <div className="sb-footer">
        {creatingStore ? (
          <div className="create-inline">
            <input
              placeholder="知識庫名稱..."
              value={newStoreName}
              onChange={(e) => setNewStoreName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCreateStore()}
              autoFocus
            />
            <div className="create-actions">
              <button className="btn btn-ghost btn-sm flex-1" onClick={() => { setCreatingStore(false); setNewStoreName(''); }}
              >
                取消
              </button>
              <button className="btn btn-primary btn-sm flex-1" onClick={handleCreateStore} disabled={!newStoreName.trim()} >
                建立
              </button>
            </div>
          </div>
        ) : (
          <button className="new-store-btn" onClick={() => setCreatingStore(true)}>
            <Plus size={14} /> 新增知識庫
          </button>
        )}
      </div>
    </aside>
  );
}
