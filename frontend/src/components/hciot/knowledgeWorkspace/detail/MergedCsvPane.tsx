import { useCallback, useEffect, useState } from 'react';
import { Table as TableIcon, Download, Edit, Save, Trash2, X } from 'lucide-react';

import type { HciotLanguage } from '../../../../config/hciotTopics';
import { getHciotTopicMergedCsv, deleteHciotKnowledgeFile, updateHciotKnowledgeFileContent, type HciotImage, type HciotMergedCsvRow } from '../../../../services/api/hciot';
import { buildCsvString } from '../../../../utils/csv';
import { downloadBlob } from '../../../../utils/download';
import { extractUploadedImageId, rollbackUploadedImages, type DeleteImageHandler, type UploadedImageResult } from '../imageUpload';
import { getErrorMessage } from '../topicUtils';
import MergedCsvTable, { type EditableMergedCsvRow } from './MergedCsvTable';

interface MergedCsvPaneProps {
  topicId: string;
  topicLabel?: string | null;
  language: HciotLanguage;
  availableImages: HciotImage[];
  statusMessage: string | null;
  onRefreshWorkspace?: () => Promise<void> | void;
  onUploadImage?: (file: File) => Promise<UploadedImageResult>;
  onDeleteImage?: DeleteImageHandler;
  onDeleteTopic?: (topicId: string, topicLabel: string) => void;
}

const SAVE_CSV_HEADER = ['index', 'q', 'a', 'img', 'url'];
const DOWNLOAD_CSV_HEADER = ['q', 'a', 'img', 'url'];

function toCsvString(rows: HciotMergedCsvRow[]): string {
  return buildCsvString(
    SAVE_CSV_HEADER,
    rows.map((row, index) => [index + 1, row.q, row.a, row.img, row.url || '']),
  );
}

function toDownloadCsvString(rows: HciotMergedCsvRow[]): string {
  return buildCsvString(
    DOWNLOAD_CSV_HEADER,
    rows.map((row) => [row.q, row.a, row.img, row.url || '']),
  );
}

function hasMeaningfulRowContent(row: Pick<HciotMergedCsvRow, 'q' | 'a' | 'img' | 'url'>): boolean {
  return Boolean(row.q.trim() || row.a.trim() || row.img?.trim() || row.url?.trim());
}

export default function MergedCsvPane({
  topicId,
  topicLabel,
  language,
  availableImages,
  statusMessage,
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

  const applyMergedCsvResponse = useCallback((response: { rows: EditableMergedCsvRow[]; source_files: string[] }) => {
    setRows(response.rows);
    setSourceFiles(response.source_files);
    setError(null);
  }, []);

  const fetchCsv = useCallback(async () => {
    setLoading(true);
    try {
      const response = await getHciotTopicMergedCsv(topicId, language);
      applyMergedCsvResponse(response);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [applyMergedCsvResponse, language, topicId]);

  useEffect(() => {
    setIsEditing(false);
    let active = true;
    setLoading(true);
    getHciotTopicMergedCsv(topicId, language)
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
  }, [applyMergedCsvResponse, topicId, language]);

  useEffect(() => {
    if (!isEditing) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsEditing(false);
        fetchCsv(); // revert modifications
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [fetchCsv, isEditing]);

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
      const grouped = new Map<string, HciotMergedCsvRow[]>();

      for (const row of preparedRows.filter(hasMeaningfulRowContent)) {
        const file = row.source_file ?? mainFile;
        const group = grouped.get(file) ?? [];
        group.push(row);
        grouped.set(file, group);
      }

      await Promise.all([
        ...Array.from(grouped).map(([file, fileRows]) =>
          updateHciotKnowledgeFileContent(file, toCsvString(fileRows), language)
        ),
        ...sourceFiles.filter(file => !grouped.has(file)).map(file =>
          deleteHciotKnowledgeFile(file, language)
        )
      ]);

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
  };

  const handleDeleteRow = (index: number) => {
    setRows(prev => prev.filter((_, i) => i !== index));
  };

  const handleAddRow = () => {
    setRows(prev => [
      ...prev,
      { index: String(prev.length + 1), q: '', a: '', img: '', url: '' }
    ]);
  };

  const handleDownload = () => {
    const filename = `${topicLabel || topicSlug || 'topic'}.csv`;
    const blob = new Blob([toDownloadCsvString(rows)], { type: 'text/csv;charset=utf-8' });
    downloadBlob(blob, filename);
  };

  return (
    <div className="hciot-file-editor">
      <div className="hciot-file-header">
        <div>
          <p className="hciot-file-kicker">知識庫</p>
          <h2 className="hciot-file-title">
            <TableIcon size={20} style={{ verticalAlign: '-3px', marginRight: '0.4rem' }} />
            {topicLabel || topicSlug}
          </h2>
        </div>

        <div className="hciot-file-actions">
          {isEditing ? (
            <>
              <button
                type="button"
                className="hciot-file-action-button"
                onClick={() => {
                  setIsEditing(false);
                  void fetchCsv(); // revert modifications
                }}
                disabled={saving}
              >
                <X size={15} />
                <span>取消</span>
              </button>
              <button
                type="button"
                className="hciot-file-action-button primary"
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
                className="hciot-file-action-button"
                onClick={handleDownload}
                disabled={loading || error !== null || rows.length === 0}
              >
                <Download size={15} />
                <span>下載</span>
              </button>
              {onDeleteTopic && (
                <button
                  type="button"
                  className="hciot-file-action-button danger"
                  onClick={() => onDeleteTopic(topicId, topicLabel || topicSlug || topicId)}
                  disabled={loading}
                >
                  <Trash2 size={15} />
                  <span>刪除主題</span>
                </button>
              )}
              <button
                type="button"
                className="hciot-file-action-button primary"
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
        <div className="hciot-file-status-banner">{statusMessage}</div>
      ) : null}

      <section className="hciot-file-editor-panel hciot-merged-panel">
        <MergedCsvTable
          language={language}
          rows={rows}
          sourceFiles={sourceFiles}
          availableImages={availableImages}
          loading={loading}
          error={error}
          isEditing={isEditing}
          onUpdateRow={handleUpdateRow}
          onDeleteRow={handleDeleteRow}
          onAddRow={handleAddRow}
        />
      </section>
    </div>
  );
}
