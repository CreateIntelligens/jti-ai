import { useCallback, useEffect, useState } from 'react';
import { Table as TableIcon, Download, Edit, Save, Trash2, X } from 'lucide-react';

import type { HciotLanguage } from '../../../../config/hciotTopics';
import type { HciotImage, HciotMergedCsvRow } from '../../../../services/api/hciot';
import { buildCsvString } from '../../../../utils/csv';
import { downloadBlob } from '../../../../utils/download';
import { extractUploadedImageId, rollbackUploadedImages, type DeleteImageHandler, type UploadedImageResult } from '../imageUpload';
import { getErrorMessage } from '../topicUtils';
import MergedCsvTable, { type EditableMergedCsvRow } from './MergedCsvTable';
import { useEscapeKey } from '../../../../hooks/useEscapeKey';
import { confirmDiscard } from '../../../../utils/confirmDiscard';
import type { QaWorkspaceApiClient } from '../QaKnowledgeWorkspace';

interface MergedCsvPaneProps {
  topicId: string;
  topicLabel?: string | null;
  language: HciotLanguage;
  availableImages: HciotImage[];
  statusMessage: string | null;
  api: QaWorkspaceApiClient;
  refreshKey?: number;
  // Question texts currently hidden from this topic's preset-question chips.
  // Seeds the per-row visibility checkboxes; defaults to all-visible when absent.
  hiddenQuestions?: string[];
  onRefreshWorkspace?: () => Promise<void> | void;
  onUploadImage?: (file: File) => Promise<UploadedImageResult>;
  onDeleteImage?: DeleteImageHandler;
  onDeleteTopic?: (topicId: string, topicLabel: string) => void;
}

const SAVE_CSV_HEADER = ['index', 'q', 'a', 'img', 'url'];
const DOWNLOAD_CSV_HEADER = ['index', 'q', 'a', 'img', 'url', 'display'];

// The `index` column persists each row's position in the full (drag-ordered)
// merged list — not its position within its own source file. Topics split
// across per-image `_IMG_` files rely on these global values to reconstruct
// the cross-file order on read and when syncing the topic's question list.
function toCsvString(rows: HciotMergedCsvRow[], globalIndex: Map<HciotMergedCsvRow, number>): string {
  return buildCsvString(
    SAVE_CSV_HEADER,
    rows.map((row, position) => [globalIndex.get(row) ?? position + 1, row.q, row.a, row.img, row.url || '']),
  );
}

function toDownloadCsvString(rows: HciotMergedCsvRow[], hiddenSet: Set<string>): string {
  return buildCsvString(
    DOWNLOAD_CSV_HEADER,
    rows.map((row, index) => {
      const questionText = row.q.trim();
      const display = questionText && hiddenSet.has(questionText) ? 'false' : 'true';
      return [index + 1, row.q, row.a, row.img, row.url || '', display];
    }),
  );
}

function hasMeaningfulRowContent(row: Pick<HciotMergedCsvRow, 'q' | 'a' | 'img' | 'url'>): boolean {
  return Boolean(row.q.trim() || row.a.trim() || row.img?.trim() || row.url?.trim());
}

function toHiddenQuestionSet(hiddenQuestions?: string[]): Set<string> {
  return new Set(hiddenQuestions ?? []);
}

export default function MergedCsvPane({
  topicId,
  topicLabel,
  language,
  availableImages,
  statusMessage,
  api,
  refreshKey = 0,
  hiddenQuestions,
  onRefreshWorkspace,
  onUploadImage,
  onDeleteImage,
  onDeleteTopic,
}: MergedCsvPaneProps) {
  const topicSlug = topicId.includes('/') ? topicId.split('/').pop() : topicId;

  const [loading, setLoading] = useState(true);
  const [rows, setRows] = useState<EditableMergedCsvRow[]>([]);
  const [sourceFiles, setSourceFiles] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [isEditing, setIsEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  // Question texts hidden from the topic's preset-question chips. Kept as a
  // text-keyed set (the data model's identity key). Seeded from the prop and
  // re-synced whenever the parent reloads the topic data.
  const [hiddenSet, setHiddenSet] = useState<Set<string>>(() => toHiddenQuestionSet(hiddenQuestions));

  useEffect(() => {
    setHiddenSet(toHiddenQuestionSet(hiddenQuestions));
  }, [hiddenQuestions]);

  const applyMergedCsvResponse = useCallback((response: { rows: EditableMergedCsvRow[]; source_files: string[] }) => {
    setRows(response.rows);
    setSourceFiles(response.source_files);
    setDirty(false);
    setError(null);
  }, []);

  const fetchCsv = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.getTopicMergedCsv(topicId, language);
      applyMergedCsvResponse(response);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [api, applyMergedCsvResponse, language, topicId]);

  const handleCancelEdit = useCallback(() => {
    if (dirty && !confirmDiscard('cancel')) {
      return;
    }
    setIsEditing(false);
    setHiddenSet(toHiddenQuestionSet(hiddenQuestions));
    void fetchCsv();
  }, [dirty, fetchCsv, hiddenQuestions]);

  useEffect(() => {
    setIsEditing(false);
    let active = true;
    setLoading(true);
    api.getTopicMergedCsv(topicId, language)
      .then((response) => {
        if (!active) return;
        applyMergedCsvResponse(response);
      })
      .catch((err) => {
        if (!active) return;
        setError(getErrorMessage(err));
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => { active = false; };
  }, [api, applyMergedCsvResponse, topicId, language, refreshKey]);

  useEscapeKey(handleCancelEdit, isEditing);

  const handleSave = async () => {
    if (!sourceFiles.length) return;
    setSaving(true);
    const originalRows = rows.map((row) => ({ ...row }));
    const uploadedImageIds: string[] = [];
    let imageUploadFailedIndex: number | null = null;
    let imageUploadFailedMessage: string | undefined;
    let stage: 'images' | 'save' = 'images';

    try {
      const mainFile = sourceFiles.find((f) => !f.includes('_IMG_')) ?? sourceFiles[0];
      const preparedRows = [...originalRows];

      for (const [index, row] of preparedRows.entries()) {
        if (!row.pendingImageFile) continue;
        if (!onUploadImage) {
          throw new Error('缺少圖片上傳功能');
        }

        preparedRows[index] = {
          ...row,
          imgStatus: 'uploading',
          imgError: undefined,
        };
        setRows([...preparedRows]);

        try {
          const imageId = extractUploadedImageId(await onUploadImage(row.pendingImageFile));
          uploadedImageIds.push(imageId);
          preparedRows[index] = {
            ...preparedRows[index],
            img: imageId,
            pendingImageFile: undefined,
            pendingImageName: undefined,
            imgStatus: 'done',
            imgError: undefined,
          };
          setRows([...preparedRows]);
        } catch (err: any) {
          imageUploadFailedIndex = index;
          imageUploadFailedMessage = err?.message || String(err);
          throw err;
        }
      }

      stage = 'save';
      const savedRows = preparedRows.filter(hasMeaningfulRowContent);
      const globalIndex = new Map(savedRows.map((row, position) => [row, position + 1]));
      const grouped = new Map<string, HciotMergedCsvRow[]>();

      for (const row of savedRows) {
        const file = row.source_file ?? mainFile;
        const group = grouped.get(file) ?? [];
        group.push(row);
        grouped.set(file, group);
      }

      // Hidden texts are sent alongside the batch save: the backend re-extracts
      // `questions` from the saved CSVs, so only texts that still exist among
      // the saved rows survive (matching the backend's text-keyed identity).
      const survivingQuestions = new Set(
        savedRows.map(row => row.q.trim()).filter(text => text.length > 0),
      );
      const nextHidden = Array.from(hiddenSet).filter(text => survivingQuestions.has(text));

      // One request for the whole topic: the backend writes every file, runs
      // the topic-question sync once, and applies visibility — instead of one
      // round trip (plus a redundant full-topic sync) per source file.
      await api.saveTopicMergedCsv(topicId, {
        files: Array.from(grouped).map(([file, fileRows]) => ({
          filename: file,
          content: toCsvString(fileRows, globalIndex),
        })),
        delete_files: sourceFiles.filter(file => !grouped.has(file)),
        hidden_questions: nextHidden,
      }, language);

      setIsEditing(false);
      if (onRefreshWorkspace) {
        await onRefreshWorkspace();
      }
      await fetchCsv();
    } catch (err) {
      if (stage === 'images') {
        await rollbackUploadedImages(uploadedImageIds, onDeleteImage);
        setRows(originalRows.map((row, index) => index === imageUploadFailedIndex ? {
          ...row,
          imgStatus: 'error',
          imgError: imageUploadFailedMessage,
        } : row));
      }
      alert(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const handleUpdateRow = (index: number, updated: Partial<EditableMergedCsvRow>) => {
    setRows(prev => prev.map((r, i) => i === index ? { ...r, ...updated } : r));
    setDirty(true);
  };

  const handleToggleVisible = (questionText: string, visible: boolean) => {
    if (!questionText) return;
    setHiddenSet(prev => {
      const next = new Set(prev);
      if (visible) {
        next.delete(questionText);
      } else {
        next.add(questionText);
      }
      return next;
    });
    setDirty(true);
  };

  const handleDeleteRow = (index: number) => {
    setRows(prev => prev.filter((_, i) => i !== index));
    setDirty(true);
  };

  const handleReorderRow = (fromIndex: number, toIndex: number) => {
    if (
      fromIndex === toIndex ||
      fromIndex < 0 ||
      toIndex < 0 ||
      fromIndex >= rows.length ||
      toIndex >= rows.length
    ) {
      return;
    }

    setRows(prev => {
      const next = [...prev];
      const [moved] = next.splice(fromIndex, 1);
      next.splice(toIndex, 0, moved);
      // Renumber the sequence (`index`) to the new positions so the displayed
      // 順序 (I) column matches what gets persisted.
      return next.map((row, i) => ({ ...row, index: String(i + 1) }));
    });
    setDirty(true);
  };

  const handleAddRow = () => {
    setRows(prev => [
      ...prev,
      { index: String(prev.length + 1), q: '', a: '', img: '', url: '' }
    ]);
    setDirty(true);
  };

  const handleDownload = () => {
    const filename = `${topicLabel || topicSlug || 'topic'}.csv`;
    const blob = new Blob([toDownloadCsvString(rows, hiddenSet)], { type: 'text/csv;charset=utf-8' });
    downloadBlob(blob, filename);
  };

  return (
    <div className="qa-workspace-file-editor">
      <div className="qa-workspace-file-header">
        <div>
          <p className="qa-workspace-file-kicker">知識庫</p>
          <h2 className="qa-workspace-file-title">
            <TableIcon className="qa-workspace-csv-icon" size={20} />
            {topicLabel || topicSlug}
          </h2>
        </div>

        <div className="qa-workspace-file-actions">
          {isEditing ? (
            <>
              <button
                type="button"
                className="qa-workspace-file-action-button"
                onClick={handleCancelEdit}
                disabled={saving}
              >
                <X size={15} />
                <span>取消</span>
              </button>
              <button
                type="button"
                className="qa-workspace-file-action-button primary"
                onClick={handleSave}
                disabled={saving}
              >
                <Save size={15} />
                <span>{saving ? '儲存中...' : '儲存變更'}</span>
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                className="qa-workspace-file-action-button"
                onClick={handleDownload}
                disabled={loading || error !== null || rows.length === 0}
              >
                <Download size={15} />
                <span>下載</span>
              </button>
              {onDeleteTopic && (
                <button
                  type="button"
                  className="qa-workspace-file-action-button danger"
                  onClick={() => onDeleteTopic(topicId, topicLabel || topicSlug || topicId)}
                  disabled={loading}
                >
                  <Trash2 size={15} />
                  <span>刪除主題</span>
                </button>
              )}
              <button
                type="button"
                className="qa-workspace-file-action-button primary"
                onClick={() => setIsEditing(true)}
                disabled={loading || error !== null || rows.length === 0}
              >
                <Edit size={15} />
                <span>編輯題庫</span>
              </button>
            </>
          )}
        </div>
      </div>

      {statusMessage ? (
        <div className="qa-workspace-file-status-banner">{statusMessage}</div>
      ) : null}

      <section className="qa-workspace-file-editor-panel qa-workspace-merged-panel">
        <MergedCsvTable
          language={language}
          rows={rows}
          sourceFiles={sourceFiles}
          availableImages={availableImages}
          loading={loading}
          error={error}
          isEditing={isEditing}
          hiddenQuestions={hiddenSet}
          onUpdateRow={handleUpdateRow}
          onDeleteRow={handleDeleteRow}
          onAddRow={handleAddRow}
          onToggleVisible={handleToggleVisible}
          onReorderRow={handleReorderRow}
        />
      </section>
    </div>
  );
}
