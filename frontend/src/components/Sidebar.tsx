import { useState } from 'react';
import { ChevronRight, Plus, X } from 'lucide-react';
import type { KnowledgeTarget, Store } from '../types';
import { PROJECT_COLORS, getStoreIcon, isManagedKnowledgeStore } from '../utils/storeDisplay';

interface SidebarProps {
  isOpen: boolean;
  stores: Store[];
  keyNames: string[];
  knowledgeTargets: KnowledgeTarget[];
  currentTargetId: string | null;
  onTargetChange: (targetId: string) => void;
  onCreateStore: (name: string, keyIndex: number) => Promise<void>;
  canManageKnowledge?: boolean;
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
  onTargetChange,
  onCreateStore,
  canManageKnowledge = true,
}: SidebarProps) {
  const [collapsedProjects, setCollapsedProjects] = useState<Record<string, boolean>>({});
  const [creatingForKey, setCreatingForKey] = useState<number | null>(null);
  const [newStoreName, setNewStoreName] = useState('');
  const [isCreatingStore, setIsCreatingStore] = useState(false);

  const toggleProject = (key: string) =>
    setCollapsedProjects((p) => ({ ...p, [key]: !p[key] }));

  const projectGroups = buildProjectGroups(stores, keyNames);

  const handleCreateStore = async () => {
    const keyIndex = creatingForKey ?? projectGroups[0]?.index ?? 0;
    if (!newStoreName.trim()) return;
    setIsCreatingStore(true);
    try {
      await onCreateStore(newStoreName.trim(), keyIndex);
      setNewStoreName('');
      setCreatingForKey(null);
    } finally {
      setIsCreatingStore(false);
    }
  };

  const beginCreate = (keyIndex: number) => {
    setCreatingForKey(keyIndex);
    setNewStoreName('');
    setCollapsedProjects((p) => ({ ...p, [String(keyIndex)]: false }));
  };

  const cancelCreate = () => {
    if (isCreatingStore) return;
    setCreatingForKey(null);
    setNewStoreName('');
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
              <div className="project-header">
                <button
                  type="button"
                  className="project-toggle"
                  onClick={() => toggleProject(String(group.index))}
                  aria-expanded={isOpen}
                >
                  <span className="project-dot" style={{ background: group.color }} />
                  <span className="project-name">{group.name}</span>
                  <span className={`project-chevron${isOpen ? ' open' : ''}`}>
                    <ChevronRight size={13} />
                  </span>
                </button>
                {canManageKnowledge && (
                  <button
                    type="button"
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
              </div>
              {isOpen && (
                <ul className="store-list">
                  {group.stores.length === 0 && creatingForKey !== group.index && (
                    <li className="store-empty">尚無知識庫</li>
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

      {canManageKnowledge && (
        <div className="sb-footer">
          <button
            type="button"
            className="new-store-btn"
            onClick={() => beginCreate(projectGroups[0]?.index ?? 0)}
          >
            <Plus size={14} />
            新增知識庫
          </button>
        </div>
      )}

      {canManageKnowledge && creatingForKey !== null && (
        <div className="general-modal-backdrop" onClick={cancelCreate}>
          <form
            className="general-modal"
            role="dialog"
            aria-modal="true"
            aria-label="建立知識庫"
            onSubmit={(e) => {
              e.preventDefault();
              void handleCreateStore();
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="general-modal-header">
              <h2>建立知識庫</h2>
              <button
                type="button"
                className="general-modal-close"
                onClick={cancelCreate}
                aria-label="關閉"
                disabled={isCreatingStore}
              >
                <X size={16} />
              </button>
            </div>
            <label className="general-form-field">
              <span>名稱</span>
              <input
                value={newStoreName}
                autoFocus
                onChange={(e) => setNewStoreName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') cancelCreate();
                }}
              />
            </label>
            <label className="general-form-field">
              <span>專案</span>
              <select
                value={creatingForKey}
                onChange={(e) => setCreatingForKey(Number(e.target.value))}
              >
                {projectGroups.map((group) => (
                  <option key={group.index} value={group.index}>
                    {group.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="general-modal-actions">
              <button
                type="button"
                className="btn btn-ghost"
                onClick={cancelCreate}
                disabled={isCreatingStore}
              >
                取消
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={!newStoreName.trim() || isCreatingStore}
              >
                {isCreatingStore ? '建立中...' : '建立'}
              </button>
            </div>
          </form>
        </div>
      )}

    </aside>
  );
}
