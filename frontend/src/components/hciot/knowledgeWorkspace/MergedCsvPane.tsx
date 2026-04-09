import { useEffect, useState } from 'react';
import { Table as TableIcon, Edit, Save, X } from 'lucide-react';

import type { HciotLanguage } from '../../../config/hciotTopics';
import { getHciotTopicMergedCsv, deleteHciotKnowledgeFile, updateHciotKnowledgeFileContent, type HciotImage, type HciotMergedCsvRow } from '../../../services/api/hciot';
import { extractUploadedImageId, rollbackUploadedImages, type DeleteImageHandler, type UploadedImageResult } from './imageUpload';
import { getErrorMessage } from './shared';
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
}

function toCsvString(rows: HciotMergedCsvRow[]): string {
  const header = ['index', 'q', 'a', 'img'];
  const escape = (val: any) => {
    const str = val == null ? '' : String(val);
    if (str.includes(',') || str.includes('"') || str.includes('\n')) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    return `"${str}"`;
  };

  const lines = [
    header.map(escape).join(','),
    ...rows.map((r, i) => [i + 1, r.q, r.a, r.img].map(escape).join(','))
  ];
  return lines.join('\n');
}

function hasMeaningfulRowContent(row: Pick<HciotMergedCsvRow, 'q' | 'a' | 'img'>): boolean {
  return Boolean(row.q.trim() || row.a.trim() || row.img?.trim());
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
}: MergedCsvPaneProps) {
  const topicSlug = topicId.includes('/') ? topicId.split('/').pop() : topicId;

  const [loading, setLoading] = useState(true);
  const [rows, setRows] = useState<EditableMergedCsvRow[]>([]);
  const [sourceFiles, setSourceFiles] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [isEditing, setIsEditing] = useState(false);
  const [saving, setSaving] = useState(false);

  const applyMergedCsvResponse = (response: { rows: EditableMergedCsvRow[]; source_files: string[] }) => {
    setRows(response.rows);
    setSourceFiles(response.source_files);
    setError(null);
  };

  const fetchCsv = async () => {
    setLoading(true);
    try {
      const response = await getHciotTopicMergedCsv(topicId, language);
      applyMergedCsvResponse(response);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

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
  }, [topicId, language]);

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
  }, [isEditing, topicId, language]); // added topicId/language to ensure it uses fresh fetchCsv if somehow changed

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
          throw new Error(language === 'zh' ? '缺少圖片上傳功能' : 'Image upload is unavailable');
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
      console.error('Failed to save merged CSV:', err);
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
      { index: String(prev.length + 1), q: '', a: '', img: '' }
    ]);
  };

  return (
    <div className="hciot-file-editor">
      <div className="hciot-file-header">
        <div>
          <p className="hciot-file-kicker">Knowledge Explorer</p>
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
                <span>{language === 'zh' ? '取消' : 'Cancel'}</span>
              </button>
              <button
                type="button"
                className="hciot-file-action-button primary"
                onClick={handleSave}
                disabled={saving}
              >
                <Save size={15} />
                <span>{saving ? (language === 'zh' ? '儲存中...' : 'Saving...') : (language === 'zh' ? '儲存變更' : 'Save Changes')}</span>
              </button>
            </>
          ) : (
            <button
              type="button"
              className="hciot-file-action-button"
              onClick={() => setIsEditing(true)}
              disabled={loading || error !== null || rows.length === 0}
            >
              <Edit size={15} />
              <span>{language === 'zh' ? '編輯題庫' : 'Edit Q&A'}</span>
            </button>
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
