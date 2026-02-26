import { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import * as api from '../services/api';
import JtiPersonaTab from './jti/JtiPersonaTab';
import JtiKnowledgeTab from './jti/JtiKnowledgeTab';
import Tabs from './Tabs';
import type { Tab } from './Tabs';

interface Prompt {
  id: string;
  name: string;
  content: string;
  created_at: string;
  updated_at: string;
  is_default?: boolean;
  readonly?: boolean;
  is_active?: boolean;
}

interface JtiSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onPromptChange: () => void;
  language?: string;
}

interface KBFile { name: string; display_name: string; size?: number; editable?: boolean; }

const MAX_CUSTOM = 3;
const SYSTEM_DEFAULT_ID = 'system_default';
const normalizeLanguage = (value?: string) => (
  typeof value === 'string' && value.trim().toLowerCase().startsWith('en') ? 'en' : 'zh'
);

export default function JtiSettingsModal({ isOpen, onClose, onPromptChange, language = 'zh' }: JtiSettingsModalProps) {
  const normalizedLanguage = normalizeLanguage(language);
  const [activeTab, setActiveTab] = useState<'prompt' | 'quiz' | 'kb'>('prompt');

  // === Prompt state ===
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [activePromptId, setActivePromptId] = useState<string | null>(null);
  const [maxCustom, setMaxCustom] = useState(MAX_CUSTOM);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editContent, setEditContent] = useState('');
  const [cloning, setCloning] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [runtimeSettings, setRuntimeSettings] = useState<api.JtiRuntimeSettings | null>(null);
  const [runtimePromptId, setRuntimePromptId] = useState<string>(SYSTEM_DEFAULT_ID);
  const [defaultRuntimeSettings, setDefaultRuntimeSettings] = useState<api.JtiRuntimeSettings | null>(null);
  const [savingRuntimeSettings, setSavingRuntimeSettings] = useState(false);

  // === KB state ===
  const [kbFiles, setKbFiles] = useState<KBFile[]>([]);
  const [kbLoading, setKbLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [confirmDeleteFile, setConfirmDeleteFile] = useState<string | null>(null);
  const [deletingFile, setDeletingFile] = useState(false);

  // === File viewer state ===
  const [viewingFile, setViewingFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>('');
  const [fileEditable, setFileEditable] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [fileEditContent, setFileEditContent] = useState('');
  const [saving, setSaving] = useState(false);
  const [fileLoading, setFileLoading] = useState(false);

  const resolveRuntimePromptId = (promptId?: string | null) => promptId || SYSTEM_DEFAULT_ID;

  useEffect(() => {
    if (isOpen) {
      const init = async () => {
        const latestActivePromptId = await loadPrompts();
        await refreshRuntimeSettings(latestActivePromptId);
      };
      void init();
    }
  }, [isOpen, normalizedLanguage]);

  useEffect(() => {
    if (isOpen && activeTab === 'kb') {
      void loadKbFiles();
    }
  }, [isOpen, activeTab, normalizedLanguage]);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        if (confirmDeleteId || confirmDeleteFile) {
          setConfirmDeleteId(null);
          setConfirmDeleteFile(null);
        } else if (viewingFile) {
          if (isEditing) handleCancelFileEdit();
          else closeViewer();
        } else if (editingId) {
          cancelEdit();
        } else {
          onClose();
        }
      }
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [isOpen, onClose, editingId, confirmDeleteId, confirmDeleteFile, viewingFile, isEditing]);

  // === Prompt handlers ===
  const loadPrompts = async (): Promise<string | null> => {
    setLoading(true);
    try {
      const data = await api.listJtiPrompts(normalizedLanguage);
      setPrompts(data.prompts || []);
      const latestActivePromptId = data.active_prompt_id || null;
      setActivePromptId(latestActivePromptId);
      setMaxCustom(data.max_custom_prompts || MAX_CUSTOM);
      return latestActivePromptId;
    } catch (e) {
      console.error('Failed to load JTI prompts:', e);
      return null;
    } finally {
      setLoading(false);
    }
  };

  const loadRuntimeSettings = async (promptId: string) => {
    try {
      const data = await api.getJtiRuntimeSettings(promptId, normalizedLanguage);
      setRuntimeSettings(data.settings || null);
      setRuntimePromptId(promptId);
    } catch (e) {
      console.error('Failed to load JTI runtime settings:', e);
    }
  };

  const loadDefaultRuntimeSettings = async () => {
    try {
      const data = await api.getJtiRuntimeSettings(SYSTEM_DEFAULT_ID, normalizedLanguage);
      setDefaultRuntimeSettings(data.settings || null);
    } catch (e) {
      console.error('Failed to load default JTI runtime settings:', e);
    }
  };

  const refreshRuntimeSettings = async (latestActivePromptId: string | null) => {
    const targetPromptId = resolveRuntimePromptId(latestActivePromptId);
    await Promise.all([loadRuntimeSettings(targetPromptId), loadDefaultRuntimeSettings()]);
  };

  const handleSelectRuntimePrompt = async (promptId: string) => {
    if (promptId === SYSTEM_DEFAULT_ID) {
      setRuntimePromptId(SYSTEM_DEFAULT_ID);
      return;
    }
    await loadRuntimeSettings(promptId);
  };

  const handleCreate = async (name: string, content: string) => {
    setCreating(true);
    try {
      await api.createJtiPrompt(name, content, normalizedLanguage);
      const latestActivePromptId = await loadPrompts();
      await refreshRuntimeSettings(latestActivePromptId);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      alert('建立失敗: ' + msg);
    } finally {
      setCreating(false);
    }
  };

  const handleCloneDefault = async () => {
    setCloning(true);
    try {
      await api.cloneDefaultJtiPrompt(normalizedLanguage);
      const latestActivePromptId = await loadPrompts();
      await refreshRuntimeSettings(latestActivePromptId);
      onPromptChange();
      setSuccessMsg('✅ 已複製預設人物設定並啟用');
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      alert('複製失敗: ' + msg);
    } finally {
      setCloning(false);
    }
  };

  const handleSetActive = async (promptId: string | null) => {
    try {
      await api.setActiveJtiPrompt(promptId, normalizedLanguage);
      const latestActivePromptId = await loadPrompts();
      await refreshRuntimeSettings(latestActivePromptId);
      onPromptChange();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      alert('設定失敗: ' + msg);
    }
  };

  const startEdit = (prompt: Prompt) => {
    setEditingId(prompt.id);
    setEditName(prompt.name);
    setEditContent(prompt.content);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditName('');
    setEditContent('');
  };

  const saveEdit = async () => {
    if (!editingId) return;
    try {
      await api.updateJtiPrompt(editingId, editName, editContent, normalizedLanguage);
      const latestActivePromptId = await loadPrompts();
      await refreshRuntimeSettings(latestActivePromptId);
      if (editingId === activePromptId) onPromptChange();
      cancelEdit();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      alert('更新失敗: ' + msg);
    }
  };

  const handleDeleteClick = (promptId: string) => setConfirmDeleteId(promptId);
  const handleDeleteCancel = () => setConfirmDeleteId(null);

  const handleDeleteConfirm = async () => {
    if (!confirmDeleteId) return;
    const promptId = confirmDeleteId;
    setDeleting(true);
    try {
      await api.deleteJtiPrompt(promptId, normalizedLanguage);
      setConfirmDeleteId(null);
      const latestActivePromptId = await loadPrompts();
      await refreshRuntimeSettings(latestActivePromptId);
      if (promptId === activePromptId) onPromptChange();
      setSuccessMsg('✅ 已刪除人物設定');
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      alert('刪除失敗: ' + msg);
    } finally {
      setDeleting(false);
    }
  };

  const handleSaveRuntimeSettings = async (
    settings: api.JtiRuntimeSettings,
    promptId: string,
  ) => {
    if (!promptId || promptId === SYSTEM_DEFAULT_ID) {
      alert('預設人物設定的回覆規則為唯讀，請先建立副本並啟用後再編輯。');
      return;
    }

    setSavingRuntimeSettings(true);
    try {
      const result = await api.updateJtiRuntimeSettings(settings, promptId, normalizedLanguage);
      setRuntimeSettings(result.settings);
      setRuntimePromptId(promptId);
      if (promptId === activePromptId) onPromptChange();
      setSuccessMsg('✅ 已更新回覆規則');
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      alert('儲存設定失敗: ' + msg);
    } finally {
      setSavingRuntimeSettings(false);
    }
  };

  // === KB handlers ===
  const loadKbFiles = async () => {
    setKbLoading(true);
    try {
      const data = await api.listJtiKnowledgeFiles(normalizedLanguage);
      setKbFiles(data.files || []);
    } catch (e) {
      console.error('Failed to load KB files:', e);
    } finally {
      setKbLoading(false);
    }
  };

  const handleUploadFiles = async (files: FileList | File[]) => {
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        await api.uploadJtiKnowledgeFile(normalizedLanguage, file);
      }
      await loadKbFiles();
      setSuccessMsg(`✅ 已上傳 ${files.length} 個檔案`);
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      alert('上傳失敗: ' + msg);
    } finally {
      setUploading(false);
    }
  };

  const handleViewFile = async (filename: string) => {
    setViewingFile(filename);
    setFileLoading(true);
    setIsEditing(false);
    try {
      const data = await api.getJtiKnowledgeFileContent(filename, normalizedLanguage);
      setFileContent(data.content || '');
      setFileEditable(data.editable || false);
    } catch {
      setFileContent('無法載入檔案內容');
      setFileEditable(false);
    } finally {
      setFileLoading(false);
    }
  };

  const handleDownloadFile = async (filename: string) => {
    try {
      await api.downloadJtiKnowledgeFile(filename, normalizedLanguage);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      alert('下載失敗: ' + msg);
    }
  };

  const handleStartFileEdit = () => { setFileEditContent(fileContent); setIsEditing(true); };
  const handleCancelFileEdit = () => setIsEditing(false);

  const handleSaveFileEdit = async () => {
    if (!viewingFile) return;
    setSaving(true);
    try {
      await api.updateJtiKnowledgeFileContent(viewingFile, fileEditContent, normalizedLanguage);
      setFileContent(fileEditContent);
      setIsEditing(false);
      setSuccessMsg('✅ 已儲存變更');
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      alert('儲存失敗: ' + msg);
    } finally {
      setSaving(false);
    }
  };

  const closeViewer = () => { setViewingFile(null); setFileContent(''); setIsEditing(false); };

  const handleDeleteFileClick = (fileName: string) => setConfirmDeleteFile(fileName);
  const handleDeleteFileCancel = () => setConfirmDeleteFile(null);

  const handleDeleteFileConfirm = async () => {
    if (!confirmDeleteFile) return;
    setDeletingFile(true);
    try {
      await api.deleteJtiKnowledgeFile(confirmDeleteFile, normalizedLanguage);
      setConfirmDeleteFile(null);
      await loadKbFiles();
      setSuccessMsg('✅ 已刪除檔案');
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      alert('刪除失敗: ' + msg);
    } finally {
      setDeletingFile(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="jti-settings-overlay" onClick={onClose}>
      <div className="jti-settings-modal" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="jti-settings-header">
          <h2 className="jti-settings-title">設定</h2>
          <button className="jti-settings-close" onClick={onClose} aria-label="關閉">
            <X size={20} />
          </button>
        </div>

        {/* Tabs */}
        <Tabs
          tabs={[
            { key: 'prompt', label: '人物設定' },
            { key: 'quiz', label: '題庫', disabled: true, title: '即將推出' },
            { key: 'kb', label: '知識庫', onClick: loadKbFiles },
          ] as Tab[]}
          activeKey={activeTab}
          onChange={(key) => setActiveTab(key as 'prompt' | 'quiz' | 'kb')}
        />

        {/* Content */}
        <div className="jti-settings-content">
          {activeTab === 'prompt' && (
            <JtiPersonaTab
              prompts={prompts}
              maxCustom={maxCustom}
              loading={loading}
              successMsg={successMsg}
              language={normalizedLanguage}
              onSetActive={handleSetActive}
              onCloneDefault={handleCloneDefault}
              cloning={cloning}
              onCreate={handleCreate}
              creating={creating}
              onStartEdit={startEdit}
              editingId={editingId}
              editName={editName}
              editContent={editContent}
              onEditNameChange={setEditName}
              onEditContentChange={setEditContent}
              onSaveEdit={saveEdit}
              onCancelEdit={cancelEdit}
              onDeleteClick={handleDeleteClick}
              confirmDeleteId={confirmDeleteId}
              deleting={deleting}
              onDeleteConfirm={handleDeleteConfirm}
              onDeleteCancel={handleDeleteCancel}
              runtimeSettings={runtimeSettings}
              runtimePromptId={runtimePromptId}
              defaultRuntimeSettings={defaultRuntimeSettings}
              savingRuntimeSettings={savingRuntimeSettings}
              onSelectRuntimePrompt={handleSelectRuntimePrompt}
              onSaveRuntimeSettings={handleSaveRuntimeSettings}
            />
          )}

          {activeTab === 'quiz' && (
            <div className="jti-settings-coming-soon">
              即將推出
            </div>
          )}

          {activeTab === 'kb' && (
            <JtiKnowledgeTab
              language={normalizedLanguage}
              kbFiles={kbFiles}
              kbLoading={kbLoading}
              uploading={uploading}
              successMsg={successMsg}
              onUploadFiles={handleUploadFiles}
              onViewFile={handleViewFile}
              onDownloadFile={handleDownloadFile}
              onDeleteFileClick={handleDeleteFileClick}
              confirmDeleteFile={confirmDeleteFile}
              deletingFile={deletingFile}
              onDeleteFileConfirm={handleDeleteFileConfirm}
              onDeleteFileCancel={handleDeleteFileCancel}
              viewingFile={viewingFile}
              fileContent={fileContent}
              fileEditable={fileEditable}
              fileLoading={fileLoading}
              isEditing={isEditing}
              fileEditContent={fileEditContent}
              saving={saving}
              onStartEdit={handleStartFileEdit}
              onCancelEdit={handleCancelFileEdit}
              onSaveEdit={handleSaveFileEdit}
              onFileEditContentChange={setFileEditContent}
              onCloseViewer={closeViewer}
            />
          )}
        </div>
      </div>
    </div>
  );
}
