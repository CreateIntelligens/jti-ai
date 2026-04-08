import { useEffect, useState } from 'react';
import { Table as TableIcon, Edit, Save, X } from 'lucide-react';

import type { HciotLanguage } from '../../../config/hciotTopics';
import { getHciotTopicMergedCsv, deleteHciotKnowledgeFile, updateHciotKnowledgeFileContent, type HciotMergedCsvRow } from '../../../services/api/hciot';
import { getErrorMessage } from './shared';
import MergedCsvTable from './MergedCsvTable';

interface MergedCsvPaneProps {
  topicId: string;
  topicLabel?: string | null;
  language: HciotLanguage;
  statusMessage: string | null;
  onRefreshWorkspace?: () => void;
  onUploadImage?: (file: File) => Promise<{ image_id: string }>;
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

export default function MergedCsvPane({
  topicId,
  topicLabel,
  language,
  statusMessage,
  onRefreshWorkspace,
  onUploadImage,
}: MergedCsvPaneProps) {
  const topicSlug = topicId.includes('/') ? topicId.split('/').pop() : topicId;

  const [loading, setLoading] = useState(true);
  const [rows, setRows] = useState<HciotMergedCsvRow[]>([]);
  const [sourceFiles, setSourceFiles] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [isEditing, setIsEditing] = useState(false);
  const [saving, setSaving] = useState(false);

  const fetchCsv = () => {
    let active = true;
    setLoading(true);
    getHciotTopicMergedCsv(topicId, language)
      .then(res => {
        if (active) {
          setRows(res.rows);
          setSourceFiles(res.source_files);
          setLoading(false);
        }
      })
      .catch(err => {
        if (active) {
          setError(getErrorMessage(err));
          setLoading(false);
        }
      });
    return () => { active = false; };
  };

  useEffect(() => {
    setIsEditing(false);
    return fetchCsv();
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
    try {
      const mainFile = sourceFiles.find((f) => !f.includes('_IMG_')) ?? sourceFiles[0];
      const grouped = new Map<string, HciotMergedCsvRow[]>();

      for (const row of rows) {
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
      onRefreshWorkspace ? onRefreshWorkspace() : fetchCsv();
    } catch (err) {
      console.error('Failed to save merged CSV:', err);
      alert(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const handleUpdateRow = (index: number, updated: Partial<HciotMergedCsvRow>) => {
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
                  fetchCsv(); // revert modifications
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
          topicId={topicId}
          language={language}
          rows={rows}
          sourceFiles={sourceFiles}
          loading={loading}
          error={error}
          isEditing={isEditing}
          onUpdateRow={handleUpdateRow}
          onDeleteRow={handleDeleteRow}
          onAddRow={handleAddRow}
          onUploadImage={onUploadImage}
        />
      </section>
    </div>
  );
}
