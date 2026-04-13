import { useEffect, useState } from 'react';
import { X } from 'lucide-react';

import { normalizeHciotLanguage } from '../config/hciotTopics';
import * as api from '../services/api';
import JtiPersonaTab from './jti/JtiPersonaTab';

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

interface HciotSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onPromptChange: () => void;
  language?: string;
}

const MAX_CUSTOM = 3;
const SYSTEM_DEFAULT_ID = 'system_default';

export default function HciotSettingsModal({
  isOpen,
  onClose,
  onPromptChange,
  language = 'zh',
}: HciotSettingsModalProps) {
  const normalizedLanguage = normalizeHciotLanguage(language);
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [activePromptId, setActivePromptId] = useState<string | null>(null);
  const [maxCustom, setMaxCustom] = useState(MAX_CUSTOM);
  const [loading, setLoading] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editContent, setEditContent] = useState('');
  const [cloning, setCloning] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [runtimeSettings, setRuntimeSettings] = useState<api.HciotRuntimeSettings | null>(null);
  const [runtimePromptId, setRuntimePromptId] = useState<string>(SYSTEM_DEFAULT_ID);
  const [defaultRuntimeSettings, setDefaultRuntimeSettings] = useState<api.HciotRuntimeSettings | null>(null);
  const [savingRuntimeSettings, setSavingRuntimeSettings] = useState(false);

  const resolveRuntimePromptId = (promptId?: string | null) => promptId || SYSTEM_DEFAULT_ID;

  const loadPrompts = async (): Promise<string | null> => {
    setLoading(true);
    try {
      const data = await api.listHciotPrompts(normalizedLanguage);
      setPrompts(data.prompts || []);
      const latestActivePromptId = data.active_prompt_id || null;
      setActivePromptId(latestActivePromptId);
      setMaxCustom(data.max_custom_prompts || MAX_CUSTOM);
      return latestActivePromptId;
    } catch (error) {
      console.error('Failed to load HCIoT prompts:', error);
      return null;
    } finally {
      setLoading(false);
    }
  };

  const loadRuntimeSettings = async (promptId: string) => {
    try {
      const data = await api.getHciotRuntimeSettings(promptId, normalizedLanguage);
      setRuntimeSettings(data.settings || null);
      setRuntimePromptId(promptId);
    } catch {
      setRuntimeSettings(null);
      setRuntimePromptId(SYSTEM_DEFAULT_ID);
    }
  };

  const loadDefaultRuntimeSettings = async () => {
    try {
      const data = await api.getHciotRuntimeSettings(SYSTEM_DEFAULT_ID, normalizedLanguage);
      setDefaultRuntimeSettings(data.settings || null);
    } catch (error) {
      console.error('Failed to load default HCIoT runtime settings:', error);
    }
  };

  const refreshRuntimeSettings = async (latestActivePromptId: string | null) => {
    await loadRuntimeSettings(resolveRuntimePromptId(latestActivePromptId));
  };

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const init = async () => {
      const latestActivePromptId = await loadPrompts();
      await Promise.all([
        refreshRuntimeSettings(latestActivePromptId),
        loadDefaultRuntimeSettings(),
      ]);
    };

    void init();
  }, [isOpen, normalizedLanguage]);

  useEffect(() => {
    const handleEsc = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || !isOpen) {
        return;
      }

      if (confirmDeleteId) {
        setConfirmDeleteId(null);
        return;
      }

      if (editingId) {
        setEditingId(null);
        setEditName('');
        setEditContent('');
        return;
      }

      onClose();
    };

    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [confirmDeleteId, editingId, isOpen, onClose]);

  const handleSelectRuntimePrompt = async (promptId: string) => {
    if (promptId === SYSTEM_DEFAULT_ID) {
      setRuntimePromptId(SYSTEM_DEFAULT_ID);
      return;
    }
    await loadRuntimeSettings(promptId);
  };


  const handleCloneDefault = async () => {
    setCloning(true);
    try {
      await api.cloneDefaultHciotPrompt(normalizedLanguage);
      const latestActivePromptId = await loadPrompts();
      await refreshRuntimeSettings(latestActivePromptId);
      onPromptChange();
      setSuccessMsg('✅ 已複製預設衛教助手設定並啟用');
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (error) {
      alert(`複製失敗: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setCloning(false);
    }
  };

  const handleSetActive = async (promptId: string | null) => {
    // Optimistic update so UI reacts before the server round-trip completes.
    setActivePromptId(promptId);
    setRuntimePromptId(resolveRuntimePromptId(promptId));
    setPrompts(prev =>
      prev.map(p => ({
        ...p,
        is_active: promptId ? p.id === promptId : p.id === SYSTEM_DEFAULT_ID,
      })),
    );

    try {
      await api.setActiveHciotPrompt(promptId, normalizedLanguage);
      const latestActivePromptId = await loadPrompts();
      await refreshRuntimeSettings(latestActivePromptId);
      onPromptChange();
    } catch (error) {
      await refreshRuntimeSettings(await loadPrompts());
      alert(`設定失敗: ${error instanceof Error ? error.message : String(error)}`);
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
    if (!editingId) {
      return;
    }
    try {
      await api.updateHciotPrompt(editingId, editName, editContent, normalizedLanguage);
      const latestActivePromptId = await loadPrompts();
      await refreshRuntimeSettings(latestActivePromptId);
      if (editingId === activePromptId) {
        onPromptChange();
      }
      cancelEdit();
    } catch (error) {
      alert(`更新失敗: ${error instanceof Error ? error.message : String(error)}`);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!confirmDeleteId) {
      return;
    }

    const promptId = confirmDeleteId;
    const wasActive = promptId === activePromptId;
    setDeleting(true);
    try {
      await api.deleteHciotPrompt(promptId, normalizedLanguage);
      setConfirmDeleteId(null);

      if (wasActive) {
        setActivePromptId(null);
        setRuntimePromptId(SYSTEM_DEFAULT_ID);
        setPrompts(prev =>
          prev
            .filter(p => p.id !== promptId)
            .map(p => p.id === SYSTEM_DEFAULT_ID ? { ...p, is_active: true } : p),
        );
      } else {
        setPrompts(prev => prev.filter(p => p.id !== promptId));
      }

      const latestActivePromptId = await loadPrompts();
      await refreshRuntimeSettings(latestActivePromptId);

      if (wasActive) {
        onPromptChange();
      }
      setSuccessMsg('✅ 已刪除衛教助手設定');
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (error) {
      alert(`刪除失敗: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setDeleting(false);
    }
  };

  const handleSaveRuntimeSettings = async (
    settings: api.HciotRuntimeSettings,
    promptId: string,
  ) => {
    if (!promptId || promptId === SYSTEM_DEFAULT_ID) {
      alert('預設設定為唯讀，請先建立副本並啟用後再編輯。');
      return;
    }

    setSavingRuntimeSettings(true);
    try {
      const result = await api.updateHciotRuntimeSettings(settings, promptId, normalizedLanguage);
      setRuntimeSettings(result.settings);
      setRuntimePromptId(promptId);
      if (promptId === activePromptId) {
        onPromptChange();
      }
      setSuccessMsg('✅ 已更新回覆規則');
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (error) {
      alert(`儲存設定失敗: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setSavingRuntimeSettings(false);
    }
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div className="jti-settings-overlay" onClick={onClose}>
      <div className="jti-settings-modal" onClick={(event) => event.stopPropagation()}>
        <div className="jti-settings-header">
          <h2 className="jti-settings-title">HCIoT 設定</h2>
          <button className="jti-settings-close" onClick={onClose} aria-label="關閉">
            <X size={20} />
          </button>
        </div>

        <div className="jti-settings-content">
          <JtiPersonaTab
            prompts={prompts}
            maxCustom={maxCustom}
            loading={loading}
            successMsg={successMsg}
            language={normalizedLanguage}
            onSetActive={handleSetActive}
            onCloneDefault={handleCloneDefault}
            cloning={cloning}
            showCreateForm={false}
            onStartEdit={startEdit}
            editingId={editingId}
            editName={editName}
            editContent={editContent}
            onEditNameChange={setEditName}
            onEditContentChange={setEditContent}
            onSaveEdit={saveEdit}
            onCancelEdit={cancelEdit}
            onDeleteClick={setConfirmDeleteId}
            confirmDeleteId={confirmDeleteId}
            deleting={deleting}
            onDeleteConfirm={handleDeleteConfirm}
            onDeleteCancel={() => setConfirmDeleteId(null)}
            runtimeSettings={runtimeSettings}
            runtimePromptId={runtimePromptId}
            defaultRuntimeSettings={defaultRuntimeSettings}
            savingRuntimeSettings={savingRuntimeSettings}
            onSelectRuntimePrompt={handleSelectRuntimePrompt}
            onSaveRuntimeSettings={handleSaveRuntimeSettings}
          />
        </div>
      </div>
    </div>
  );
}
