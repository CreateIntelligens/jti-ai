import { useCallback, useEffect, useMemo, useState, type CSSProperties } from 'react';
import { GripVertical, X } from 'lucide-react';
import {
  DndContext,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type CollisionDetection,
  type DragEndEvent,
} from '@dnd-kit/core';
import { SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

import type { QaAdminCategory } from '../../../../config/qaTopics';
import { moveItem } from '../topicUtils';

type EditableCategory = QaAdminCategory;

interface VisibilityChanges {
  categoryHidden: Array<{ categoryId: string; hidden: boolean }>;
  topicHidden: Array<{ topicId: string; hidden: boolean }>;
}

interface VisibilityOrderModalProps {
  open: boolean;
  categories: QaAdminCategory[];
  saving: boolean;
  onClose: () => void;
  onSave: (categories: QaAdminCategory[], changes: VisibilityChanges) => Promise<void> | void;
}

function categoryDragId(categoryId: string): string {
  return `category:${categoryId}`;
}

function topicDragId(topicId: string): string {
  return `topic:${topicId}`;
}

function parseDragId(value: string): { kind: 'category' | 'topic' | null; id: string } {
  const separatorIndex = value.indexOf(':');
  if (separatorIndex === -1) {
    return { kind: null, id: value };
  }
  const kind = value.slice(0, separatorIndex);
  const id = value.slice(separatorIndex + 1);
  return {
    kind: kind === 'category' || kind === 'topic' ? kind : null,
    id,
  };
}

export function getVisibilityOrderCollisionIds(
  activeId: string,
  droppableIds: string[],
  topicOwnerByDragId: Map<string, string>,
): string[] {
  const activeItem = parseDragId(activeId);
  if (activeItem.kind === 'category') {
    return droppableIds.filter((droppableId) => parseDragId(droppableId).kind === 'category');
  }

  if (activeItem.kind === 'topic') {
    const ownerCategoryId = topicOwnerByDragId.get(activeId);
    if (!ownerCategoryId) {
      return [];
    }
    return droppableIds.filter((droppableId) => topicOwnerByDragId.get(droppableId) === ownerCategoryId);
  }

  return droppableIds;
}

function cloneCategories(categories: QaAdminCategory[]): EditableCategory[] {
  return categories.map((category) => ({
    ...category,
    hidden: Boolean(category.hidden),
    topics: category.topics.map((topic) => ({
      ...topic,
      hidden: Boolean(topic.hidden),
    })),
  }));
}

function collectChanges(
  originalCategories: QaAdminCategory[],
  categories: QaAdminCategory[],
): VisibilityChanges {
  const originalCategoryHidden = new Map(
    originalCategories.map((category) => [category.id, Boolean(category.hidden)]),
  );
  const originalTopicHidden = new Map(
    originalCategories.flatMap((category) =>
      category.topics.map((topic) => [topic.id, Boolean(topic.hidden)] as const)
    ),
  );

  return {
    categoryHidden: categories
      .filter((category) => Boolean(category.hidden) !== originalCategoryHidden.get(category.id))
      .map((category) => ({ categoryId: category.id, hidden: Boolean(category.hidden) })),
    topicHidden: categories
      .flatMap((category) => category.topics)
      .filter((topic) => Boolean(topic.hidden) !== originalTopicHidden.get(topic.id))
      .map((topic) => ({ topicId: topic.id, hidden: Boolean(topic.hidden) })),
  };
}

function SortableShell({
  id,
  className,
  children,
}: {
  id: string;
  className: string;
  children: (sortable: ReturnType<typeof useSortable>) => React.ReactNode;
}) {
  const sortable = useSortable({ id });
  const style: CSSProperties = {
    transform: CSS.Transform.toString(sortable.transform),
    transition: sortable.transition,
  };

  return (
    <div
      ref={sortable.setNodeRef}
      className={`${className}${sortable.isDragging ? ' is-dragging' : ''}`}
      style={style}
    >
      {children(sortable)}
    </div>
  );
}

export default function VisibilityOrderModal({
  open,
  categories,
  saving,
  onClose,
  onSave,
}: VisibilityOrderModalProps) {
  const [draftCategories, setDraftCategories] = useState<EditableCategory[]>(() => cloneCategories(categories));
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  useEffect(() => {
    if (open) {
      setDraftCategories(cloneCategories(categories));
    }
  }, [categories, open]);

  const categoryIds = useMemo(
    () => draftCategories.map((category) => categoryDragId(category.id)),
    [draftCategories],
  );
  const topicOwnerByDragId = useMemo(() => {
    const owners = new Map<string, string>();
    draftCategories.forEach((category) => {
      category.topics.forEach((topic) => {
        owners.set(topicDragId(topic.id), category.id);
      });
    });
    return owners;
  }, [draftCategories]);
  const collisionDetection = useCallback<CollisionDetection>((args) => {
    const allowedIds = new Set(getVisibilityOrderCollisionIds(
      String(args.active.id),
      args.droppableContainers.map((container) => String(container.id)),
      topicOwnerByDragId,
    ));

    return closestCenter({
      ...args,
      droppableContainers: args.droppableContainers.filter((container) =>
        allowedIds.has(String(container.id))
      ),
    });
  }, [topicOwnerByDragId]);

  if (!open) {
    return null;
  }

  const toggleCategory = (categoryId: string, visible: boolean) => {
    setDraftCategories((current) =>
      current.map((category) =>
        category.id === categoryId ? { ...category, hidden: !visible } : category
      )
    );
  };

  const toggleTopic = (topicId: string, visible: boolean) => {
    setDraftCategories((current) =>
      current.map((category) => ({
        ...category,
        topics: category.topics.map((topic) =>
          topic.id === topicId ? { ...topic, hidden: !visible } : topic
        ),
      }))
    );
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) {
      return;
    }

    const activeItem = parseDragId(String(active.id));
    const overItem = parseDragId(String(over.id));
    if (activeItem.kind !== overItem.kind || !activeItem.kind) {
      return;
    }

    if (activeItem.kind === 'category') {
      setDraftCategories((current) =>
        moveItem(
          current,
          current.findIndex((category) => category.id === activeItem.id),
          current.findIndex((category) => category.id === overItem.id),
        ) ?? current
      );
      return;
    }

    const categoryIndex = draftCategories.findIndex((category) =>
      category.topics.some((topic) => topic.id === activeItem.id)
    );
    if (
      categoryIndex === -1 ||
      !draftCategories[categoryIndex].topics.some((topic) => topic.id === overItem.id)
    ) {
      return;
    }

    setDraftCategories((current) => {
      const category = current[categoryIndex];
      const topics = moveItem(
        category.topics,
        category.topics.findIndex((topic) => topic.id === activeItem.id),
        category.topics.findIndex((topic) => topic.id === overItem.id),
      );
      if (!topics) return current;
      const next = [...current];
      next[categoryIndex] = { ...category, topics };
      return next;
    });
  };

  const handleSave = () => {
    void onSave(draftCategories, collectChanges(categories, draftCategories));
  };

  return (
    <div className="qa-workspace-manage-modal-backdrop">
      <div
        className="qa-workspace-manage-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="qa-workspace-manage-title"
      >
        <header className="qa-workspace-manage-header">
          <div>
            <p className="qa-workspace-file-kicker">知識庫</p>
            <h2 id="qa-workspace-manage-title" className="qa-workspace-manage-title">
              科別與主題管理
            </h2>
          </div>
          <button
            type="button"
            className="qa-workspace-explorer-icon-button"
            onClick={onClose}
            aria-label="關閉管理彈窗"
            disabled={saving}
          >
            <X size={16} />
          </button>
        </header>

        <DndContext sensors={sensors} collisionDetection={collisionDetection} onDragEnd={handleDragEnd}>
          <div className="qa-workspace-manage-tree">
            <SortableContext items={categoryIds} strategy={verticalListSortingStrategy}>
              {draftCategories.map((category) => {
                const categoryVisible = !category.hidden;
                return (
                  <SortableShell
                    key={category.id}
                    id={categoryDragId(category.id)}
                    className={`qa-workspace-manage-category${category.hidden ? ' is-hidden' : ''}`}
                  >
                    {(sortable) => (
                      <>
                        <div className="qa-workspace-manage-row">
                          <button
                            type="button"
                            className="qa-workspace-manage-grip"
                            aria-label={`拖曳科別：${category.label}`}
                            title="拖曳排序"
                            {...sortable.attributes}
                            {...sortable.listeners}
                          >
                            <GripVertical size={15} />
                          </button>
                          <label className="qa-workspace-manage-check">
                            <input
                              type="checkbox"
                              checked={categoryVisible}
                              aria-label={`顯示科別：${category.label}`}
                              onChange={(event) => toggleCategory(category.id, event.target.checked)}
                              disabled={saving}
                            />
                            <span className="qa-workspace-manage-label">{category.label}</span>
                          </label>
                        </div>
                        <SortableContext
                          items={category.topics.map((topic) => topicDragId(topic.id))}
                          strategy={verticalListSortingStrategy}
                        >
                          <div className="qa-workspace-manage-topics">
                            {category.topics.map((topic) => {
                              const topicVisible = !topic.hidden;
                              return (
                                <SortableShell
                                  key={topic.id}
                                  id={topicDragId(topic.id)}
                                  className={`qa-workspace-manage-topic${topic.hidden ? ' is-hidden' : ''}`}
                                >
                                  {(topicSortable) => (
                                    <div className="qa-workspace-manage-row topic">
                                      <button
                                        type="button"
                                        className="qa-workspace-manage-grip"
                                        aria-label={`拖曳主題：${topic.label}`}
                                        title="拖曳排序"
                                        {...topicSortable.attributes}
                                        {...topicSortable.listeners}
                                      >
                                        <GripVertical size={15} />
                                      </button>
                                      <label className="qa-workspace-manage-check">
                                        <input
                                          type="checkbox"
                                          checked={topicVisible}
                                          aria-label={`顯示主題：${topic.label}`}
                                          onChange={(event) => toggleTopic(topic.id, event.target.checked)}
                                          disabled={saving}
                                        />
                                        <span className="qa-workspace-manage-label">{topic.label}</span>
                                      </label>
                                    </div>
                                  )}
                                </SortableShell>
                              );
                            })}
                          </div>
                        </SortableContext>
                      </>
                    )}
                  </SortableShell>
                );
              })}
            </SortableContext>
          </div>
        </DndContext>

        <footer className="qa-workspace-manage-footer">
          <button
            type="button"
            className="qa-workspace-file-action-button"
            onClick={onClose}
            disabled={saving}
          >
            取消
          </button>
          <button
            type="button"
            className="qa-workspace-file-action-button primary"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? '儲存中...' : '儲存管理設定'}
          </button>
        </footer>
      </div>
    </div>
  );
}
