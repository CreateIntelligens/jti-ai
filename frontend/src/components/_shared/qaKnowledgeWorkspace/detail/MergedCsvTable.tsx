import { useState, type CSSProperties, type ReactNode } from 'react';
import { GripVertical, Image as ImageIcon, Loader2, Plus, Trash2, Upload, X } from 'lucide-react';
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type { HciotImage, HciotMergedCsvRow } from '../../../../services/api/hciot';
import type { HciotLanguage } from '../../../../config/hciotTopics';
import { getHciotImageUrl, normalizeImageId } from '../../../../utils/hciotImage';
import ExistingImagePicker from '../explorer/ExistingImagePicker';
import { usePendingImageUrls } from '../imageUpload';
import type { FileStatus } from '../upload/types';
import ImageLightbox from '../ImageLightbox';
import ZoomableThumbnail from '../ZoomableThumbnail';

export interface EditableMergedCsvRow extends HciotMergedCsvRow {
  pendingImageFile?: File | null;
  pendingImageName?: string;
  imgStatus?: FileStatus;
  imgError?: string;
}

function clearRowImageState(): Partial<EditableMergedCsvRow> {
  return {
    img: '',
    pendingImageFile: undefined,
    pendingImageName: undefined,
    imgStatus: 'pending',
    imgError: undefined,
  };
}

function applyExistingRowImage(imageId: string): Partial<EditableMergedCsvRow> {
  return {
    ...clearRowImageState(),
    img: imageId,
    imgStatus: 'done',
  };
}

interface MergedCsvTableProps {
  language: HciotLanguage;
  rows: EditableMergedCsvRow[];
  sourceFiles: string[];
  availableImages: HciotImage[];
  loading: boolean;
  error: string | null;
  isEditing: boolean;
  // Question texts currently hidden from the topic's preset-question chips.
  hiddenQuestions: Set<string>;
  onUpdateRow: (index: number, updated: Partial<EditableMergedCsvRow>) => void;
  onDeleteRow: (index: number) => void;
  onAddRow: () => void;
  onToggleVisible: (questionText: string, visible: boolean) => void;
  onReorderRow: (fromIndex: number, toIndex: number) => void;
}

const VISIBILITY_HINT =
  '勾選：顯示為預設問題按鈕。取消：不顯示在按鈕列，但仍會進知識庫。';

function getQuestionText(row: EditableMergedCsvRow): string {
  return row.q.trim();
}

function getQuestionVisibilityLabel(questionText: string): string {
  return questionText ? `顯示問題：${questionText}` : '顯示問題';
}

function isHttpUrl(value: string): boolean {
  return /^https?:\/\//i.test(value.trim());
}

function renderUrlValue(url?: string) {
  if (!url) {
    return null;
  }
  if (!isHttpUrl(url)) {
    return url;
  }
  return <a href={url.trim()} target="_blank" rel="noopener noreferrer">{url}</a>;
}

interface SortableRowProps {
  id: string;
  displayNumber: number;
  isEditing: boolean;
  children: ReactNode;
}

function SortableRow({ id, displayNumber, isEditing, children }: SortableRowProps) {
  const sortable = useSortable({ id, disabled: !isEditing });

  const style: CSSProperties = {
    transform: CSS.Transform.toString(sortable.transform),
    transition: sortable.transition,
  };

  const className = `qa-workspace-merged-csv-row${sortable.isDragging ? ' is-dragging' : ''}`;

  return (
    <tr ref={sortable.setNodeRef} className={className} style={style}>
      <td>
        <div className="qa-workspace-csv-row-number">
          {isEditing && (
            <button
              type="button"
              className="qa-workspace-csv-drag-handle"
              aria-label={`拖曳第 ${displayNumber} 列`}
              title="拖曳重排"
              {...sortable.attributes}
              {...sortable.listeners}
            >
              <GripVertical size={14} />
            </button>
          )}
          <span>{displayNumber}</span>
        </div>
      </td>
      {children}
    </tr>
  );
}

export default function MergedCsvTable({
  language,
  rows,
  sourceFiles,
  availableImages,
  loading,
  error,
  isEditing,
  hiddenQuestions,
  onUpdateRow,
  onDeleteRow,
  onAddRow,
  onToggleVisible,
  onReorderRow,
}: MergedCsvTableProps) {
  const pendingUrls = usePendingImageUrls(rows);
  const [pickerIndex, setPickerIndex] = useState<number | null>(null);
  const [previewImageUrl, setPreviewImageUrl] = useState<string | null>(null);

  // Require a small drag distance so clicks inside a row (textareas, buttons)
  // still work without triggering a drag. The keyboard sensor makes the grip
  // operable without a mouse (Space to pick up, ↑/↓ to move, Space to drop).
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  // Stable sortable id per row position. Reorder is resolved by looking up the
  // active/over ids within this same list, so the ids only need to be stable
  // and unique for the current render.
  const sortableIds = rows.map((_, i) => `merged-row-${i}`);

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) {
      return;
    }
    const fromIndex = sortableIds.indexOf(String(active.id));
    const toIndex = sortableIds.indexOf(String(over.id));
    if (fromIndex === -1 || toIndex === -1) {
      return;
    }
    onReorderRow(fromIndex, toIndex);
  };

  if (loading) {
    return <div className="qa-workspace-merged-csv-loading">載入整合資料中...</div>;
  }

  if (error) {
    return <div className="qa-workspace-merged-csv-error">{error}</div>;
  }

  if (rows.length === 0 && !isEditing) {
    return <div className="qa-workspace-merged-csv-empty">此主題目前沒有 CSV 檔案。</div>;
  }

  const handleFileChange = (index: number, file: File | null) => {
    if (!file || !file.type.startsWith('image/')) return;
    onUpdateRow(index, {
      img: '',
      pendingImageFile: file,
      pendingImageName: file.name,
      imgStatus: 'pending',
      imgError: undefined,
    });
  };

  const handleSelectExistingImage = (imageId: string) => {
    if (pickerIndex === null) {
      return;
    }

    const rowIndex = pickerIndex;
    setPickerIndex(null);
    onUpdateRow(rowIndex, applyExistingRowImage(imageId));
  };

  const questionTexts = Array.from(
    new Set(rows.map(getQuestionText).filter((questionText) => questionText.length > 0)),
  );
  const questionIsVisible = (questionText: string) => !hiddenQuestions.has(questionText);
  const allQuestionsVisible = questionTexts.length > 0 && questionTexts.every(questionIsVisible);
  const someQuestionsVisible = questionTexts.some(questionIsVisible);
  const isVisibilityIndeterminate = someQuestionsVisible && !allQuestionsVisible;

  const handleToggleAllVisible = (visible: boolean) => {
    questionTexts.forEach((questionText) => onToggleVisible(questionText, visible));
  };

  return (
    <div className="qa-workspace-merged-csv-container">
      <ExistingImagePicker
        open={pickerIndex !== null}
        language={language}
        images={availableImages}
        selectedImageId={pickerIndex === null ? null : (rows[pickerIndex]?.img || null)}
        onClose={() => setPickerIndex(null)}
        onSelect={handleSelectExistingImage}
      />
      <ImageLightbox
        url={previewImageUrl}
        onClose={() => setPreviewImageUrl(null)}
      />
      <div className="qa-workspace-merged-csv-meta">
        {`已合併 ${sourceFiles.length} 個檔案`}
      </div>
      <div className="qa-workspace-merged-csv-table-wrapper">
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <table className="qa-workspace-merged-csv-table">
            <thead>
              <tr>
                <th className="qa-workspace-csv-col-num">#</th>
                <th className="qa-workspace-csv-col-visible" title={VISIBILITY_HINT}>
                  {isEditing ? (
                    <div className="qa-workspace-csv-visible-header">
                      <span>顯示</span>
                      <label className="qa-workspace-csv-select-all" title="全選顯示問題">
                        <input
                          type="checkbox"
                          className="qa-workspace-csv-visible-checkbox"
                          aria-label="全選顯示問題"
                          checked={allQuestionsVisible}
                          disabled={questionTexts.length === 0}
                          ref={(el) => {
                            if (el) el.indeterminate = isVisibilityIndeterminate;
                          }}
                          onChange={(e) => handleToggleAllVisible(e.target.checked)}
                        />
                        <span>全選</span>
                      </label>
                    </div>
                  ) : (
                    <span>顯示</span>
                  )}
                </th>
                <th className="qa-workspace-csv-col-question">問題 (Q)</th>
                <th className="qa-workspace-csv-col-answer">回答 (A)</th>
                <th className="qa-workspace-csv-col-wide">圖片 (IMG)</th>
                <th className="qa-workspace-csv-col-wide">網址 (URL)</th>
                {isEditing && <th className="qa-workspace-csv-col-action">-</th>}
              </tr>
            </thead>
            <tbody>
              <SortableContext items={sortableIds} strategy={verticalListSortingStrategy}>
                {rows.map((row, i) => {
                  const hasPendingImage = Boolean(row.pendingImageFile);
                  const hasImage = Boolean(row.img || hasPendingImage);
                  const imageUrl = hasPendingImage
                    ? (row.pendingImageFile ? pendingUrls.get(row.pendingImageFile) || '' : '')
                    : getHciotImageUrl(row.img);
                  const imageLabel = row.pendingImageName || normalizeImageId(row.img) || row.img;
                  const questionText = getQuestionText(row);
                  const hasQuestionText = questionText.length > 0;
                  const isQuestionVisible = hasQuestionText && questionIsVisible(questionText);
                  const visibilityLabel = getQuestionVisibilityLabel(questionText);
                  return (
                    <SortableRow
                      key={sortableIds[i]}
                      id={sortableIds[i]}
                      displayNumber={i + 1}
                      isEditing={isEditing}
                    >
                      <td className="qa-workspace-csv-cell-center">
                        {isEditing ? (
                          <input
                            type="checkbox"
                            className="qa-workspace-csv-visible-checkbox"
                            aria-label={visibilityLabel}
                            checked={isQuestionVisible}
                            disabled={!hasQuestionText}
                            title={VISIBILITY_HINT}
                            onChange={(e) => onToggleVisible(questionText, e.target.checked)}
                          />
                        ) : (
                          <input
                            type="checkbox"
                            className="qa-workspace-csv-visible-checkbox readonly"
                            aria-label={visibilityLabel}
                            checked={isQuestionVisible}
                            readOnly
                            title={VISIBILITY_HINT}
                          />
                        )}
                      </td>
                      <td>
                        {isEditing ? (
                          <textarea
                            className="qa-workspace-file-textarea qa-workspace-csv-textarea"
                            value={row.q}
                            onChange={(e) => onUpdateRow(i, { q: e.target.value })}
                          />
                        ) : (
                          row.q
                        )}
                      </td>
                      <td className="qa-workspace-csv-cell-pre">
                        {isEditing ? (
                          <textarea
                            className="qa-workspace-file-textarea qa-workspace-csv-textarea"
                            value={row.a}
                            onChange={(e) => onUpdateRow(i, { a: e.target.value })}
                          />
                        ) : (
                          row.a
                        )}
                      </td>
                      <td>
                        {isEditing ? (
                          <div className="qa-workspace-merged-csv-img-cell">
                            {hasImage ? (
                              <div className="qa-workspace-merged-csv-img-stack">
                                <div className="qa-workspace-merged-csv-img-wrapper edit-mode">
                                  {imageUrl && (
                                    <ZoomableThumbnail
                                      src={imageUrl}
                                      alt={row.img}
                                      className="qa-workspace-merged-csv-thumbnail"
                                      onZoom={setPreviewImageUrl}
                                    />
                                  )}
                                  {row.imgStatus === 'uploading' ? (
                                    <Loader2 size={14} className="animate-spin" />
                                  ) : null}
                                  <button
                                    type="button"
                                    className="qa-workspace-merged-csv-remove-img"
                                    onClick={() => onUpdateRow(i, clearRowImageState())}
                                    title="移除圖片"
                                  >
                                    <X size={12} />
                                  </button>
                                  <span className="qa-workspace-merged-csv-img-text" title={row.imgError || imageLabel}>{imageLabel}</span>
                                </div>
                                <div className="qa-workspace-merged-csv-img-actions">
                                  <label className={`qa-workspace-merged-csv-upload-btn${row.imgStatus === 'uploading' ? ' is-uploading' : ''}`}>
                                    <input
                                      className="file-input-hidden"
                                      type="file"
                                      accept="image/*"
                                      onChange={(e) => handleFileChange(i, e.target.files?.[0] || null)}
                                      disabled={row.imgStatus === 'uploading'}
                                    />
                                    <Upload size={14} />
                                  </label>
                                  <button
                                    type="button"
                                    className="qa-workspace-merged-csv-upload-btn"
                                    onClick={() => setPickerIndex(i)}
                                  >
                                    <ImageIcon size={14} />
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <div className="qa-workspace-merged-csv-img-actions">
                                <label className={`qa-workspace-merged-csv-upload-btn${row.imgStatus === 'uploading' ? ' is-uploading' : ''}`}>
                                  <input
                                    className="file-input-hidden"
                                    type="file"
                                    accept="image/*"
                                    onChange={(e) => handleFileChange(i, e.target.files?.[0] || null)}
                                    disabled={row.imgStatus === 'uploading'}
                                  />
                                  <Upload size={14} />
                                  <span>{row.imgStatus === 'uploading' ? '...' : '上傳'}</span>
                                </label>
                                <button
                                  type="button"
                                  className="qa-workspace-merged-csv-upload-btn"
                                  onClick={() => setPickerIndex(i)}
                                >
                                  <ImageIcon size={14} />
                                  <span>既有</span>
                                </button>
                              </div>
                            )}
                          </div>
                        ) : row.img ? (
                          <div className="qa-workspace-merged-csv-img-wrapper">
                            {imageUrl && (
                              <ZoomableThumbnail
                                src={imageUrl}
                                alt={row.img}
                                className="qa-workspace-merged-csv-thumbnail"
                                title={row.img}
                                onZoom={setPreviewImageUrl}
                                onError={(e) => {
                                  (e.target as HTMLImageElement).style.display = 'none';
                                  const next = (e.target as HTMLImageElement).nextElementSibling;
                                  if (next) next.classList.remove('hidden');
                                }}
                              />
                            )}
                            <span className="qa-workspace-merged-csv-img-text hidden">{row.img}</span>
                          </div>
                        ) : null}
                      </td>
                      <td className="qa-workspace-csv-cell-break">
                        {isEditing ? (
                          <textarea
                            className="qa-workspace-file-textarea qa-workspace-csv-textarea"
                            value={row.url || ''}
                            onChange={(e) => onUpdateRow(i, { url: e.target.value })}
                          />
                        ) : renderUrlValue(row.url)}
                      </td>
                      {isEditing && (
                        <td className="qa-workspace-csv-cell-center">
                          <button
                            type="button"
                            className="qa-workspace-explorer-icon-button danger"
                            onClick={() => onDeleteRow(i)}
                            title="刪除此列"
                          >
                            <Trash2 size={15} />
                          </button>
                        </td>
                      )}
                    </SortableRow>
                  );
                })}
              </SortableContext>
            </tbody>
          </table>
        </DndContext>
        {isEditing && (
          <div className="qa-workspace-csv-footer">
            <button
              type="button"
              className="qa-workspace-file-action-button"
              onClick={onAddRow}
            >
              <Plus size={15} />
              <span>新增 Q&A</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
