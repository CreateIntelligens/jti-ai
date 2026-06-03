import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import {
  getStoreFileContent,
  updateStoreFileContent,
  getManagedKnowledgeFileContent,
  updateManagedKnowledgeFileContent,
} from '../services/api';
import type { AppTarget, FileItem, KnowledgeLanguage, Store } from '../types';
import { toErrorMessage } from '../utils/errors';
import { confirmDiscard } from '../utils/confirmDiscard';
import { useEscapeKey } from '../hooks/useEscapeKey';
import { useOverlayPressClose } from '../hooks/useOverlayPressClose';

interface FilePreviewModalProps {
  isOpen: boolean;
  store: Store | null;
  file: FileItem | null;
  onClose: () => void;
  onSaved?: () => void;
  onShowStatus?: (msg: string) => void;
}

interface LoadedContent {
  filename: string;
  editable: boolean;
  content: string | null;
  message?: string;
}

export default function FilePreviewModal({
  isOpen,
  store,
  file,
  onClose,
  onSaved,
  onShowStatus,
}: FilePreviewModalProps) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<LoadedContent | null>(null);
  const [draft, setDraft] = useState<string>('');
  const [dirty, setDirty] = useState(false);

  const fileName = file?.name || '';
  const displayName = file?.display_name || fileName;

  const requestClose = () => {
    if (dirty && !confirmDiscard('close')) return;
    onClose();
  };

  useEffect(() => {
    if (!isOpen || !store || !file) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    setDraft('');
    setDirty(false);

    const load = async () => {
      try {
        const result = store.managed_app && store.managed_language
          ? await getManagedKnowledgeFileContent(
              store.managed_app as AppTarget,
              file.name,
              store.managed_language as KnowledgeLanguage,
            )
          : await getStoreFileContent(store.name, file.name);

        if (cancelled) return;
        const loaded: LoadedContent = {
          filename: result.filename || file.name,
          editable: Boolean(result.editable),
          content: result.content ?? null,
          message: result.message,
        };
        setData(loaded);
        setDraft(loaded.content ?? '');
      } catch (e) {
        if (cancelled) return;
        setError(toErrorMessage(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => { cancelled = true; };
  }, [isOpen, store, file]);

  useEscapeKey(requestClose, isOpen);
  const overlayPressClose = useOverlayPressClose(requestClose);

  if (!isOpen || !store || !file) return null;

  const handleSave = async () => {
    if (!data?.editable) return;
    setSaving(true);
    setError(null);
    try {
      const result = store.managed_app && store.managed_language
        ? await updateManagedKnowledgeFileContent(
            store.managed_app as AppTarget,
            file.name,
            draft,
            store.managed_language as KnowledgeLanguage,
          )
        : await updateStoreFileContent(store.name, file.name, draft);

      const synced = result?.synced !== false;
      onShowStatus?.(synced ? '✅ 已儲存並重新索引' : '⚠️ 已儲存，但 RAG 同步失敗');
      setDirty(false);
      onSaved?.();
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="overlay" {...overlayPressClose}>
      <div
        className="modal file-preview-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="fpm-header">
          <div className="fpm-title">
            <h2>{displayName}</h2>
            <div className="fpm-subtitle">
              {store.display_name || store.name}
              {data && !data.editable && data.message ? ` · ${data.message}` : null}
            </div>
          </div>
          <button className="fpm-close" onClick={requestClose} title="關閉" aria-label="關閉">
            <X size={18} />
          </button>
        </div>

        <div className="fpm-body">
          {loading ? (
            <div className="fpm-status">載入中…</div>
          ) : error ? (
            <div className="fpm-status fpm-error">載入失敗: {error}</div>
          ) : !data ? null : data.content === null ? (
            <div className="fpm-status">{data.message || '此檔案格式不支援預覽'}</div>
          ) : (
            <textarea
              className="fpm-textarea"
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                setDirty(e.target.value !== (data.content ?? ''));
              }}
              readOnly={!data.editable}
              spellCheck={false}
            />
          )}
        </div>

        <div className="fpm-actions">
          <div className="fpm-actions-left">
            {data?.editable && (
              <button
                type="button"
                className="fpm-btn fpm-btn-quiet"
                onClick={() => {
                  setDraft(data.content ?? '');
                  setDirty(false);
                }}
                disabled={!dirty || saving}
              >
                還原
              </button>
            )}
          </div>
          <div className="fpm-actions-right">
            <button
              type="button"
              className="fpm-btn fpm-btn-ghost"
              onClick={requestClose}
              disabled={saving}
            >
              關閉
            </button>
            {data?.editable && (
              <button
                type="button"
                className="fpm-btn fpm-btn-primary"
                onClick={handleSave}
                disabled={saving || !dirty}
              >
                <span className="fpm-btn-label">
                  {saving ? '儲存中' : '儲存並重新索引'}
                </span>
                {saving && <span className="fpm-btn-dots" aria-hidden="true" />}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
