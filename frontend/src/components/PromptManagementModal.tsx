import { useState, useEffect, useCallback } from 'react';
import * as api from '../services/api';
import type { Store } from '../types';
import ModelSelectionTab from './settings/ModelSelectionTab';
import PromptTab from './settings/PromptTab';
import ApiKeyTab from './settings/ApiKeyTab';
import { useEscapeKey } from '../hooks/useEscapeKey';

interface Prompt {
  id: string;
  name: string;
  content: string;
  created_at: string;
  updated_at: string;
}

interface APIKey {
  id: string;
  key_prefix: string;
  name: string;
  store_name: string;
  prompt_index: number | null;
  created_at: string;
}

interface PromptItem {
  id: string;
  name: string;
  content: string;
  is_active: boolean;
}

interface PromptManagementModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentStore: string | null;
  onRestartChat: () => void | Promise<void>;
  stores: Store[];
}

export default function PromptManagementModal({
  isOpen,
  onClose,
  currentStore,
  onRestartChat,
  stores,
}: PromptManagementModalProps) {
  const [activeTab, setActiveTab] = useState<'model' | 'prompt' | 'apikey'>('model');

  // === Prompt state ===
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [activePromptId, setActivePromptId] = useState<string | null>(null);
  const [maxPrompts, setMaxPrompts] = useState(3);
  const [loading, setLoading] = useState(false);
  const [newPromptName, setNewPromptName] = useState('');
  const [newPromptContent, setNewPromptContent] = useState('');
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editContent, setEditContent] = useState('');
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [selectedModel, setSelectedModel] = useState(() =>
    localStorage.getItem('selectedModel') || 'gemini-2.5-flash-lite'
  );

  // === API Key state ===
  const [apiKeyStore, setApiKeyStore] = useState('');
  const [apiKeyName, setApiKeyName] = useState('');
  const [apiKeyPromptIndex, setApiKeyPromptIndex] = useState<string>('');
  const [apiKeyPrompts, setApiKeyPrompts] = useState<PromptItem[]>([]);
  const [apiKeys, setApiKeys] = useState<APIKey[]>([]);
  const [apiKeysLoading, setApiKeysLoading] = useState(false);
  const [apiKeyCreating, setApiKeyCreating] = useState(false);
  const [newApiKeyCreated, setNewApiKeyCreated] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen && currentStore) loadPrompts();
    if (!isOpen) setNewApiKeyCreated(null);
  }, [isOpen, currentStore]);

  useEffect(() => {
    if (isOpen && activeTab === 'apikey') loadApiKeys();
  }, [isOpen, activeTab, apiKeyStore]);

  useEffect(() => {
    if (apiKeyStore) {
      api.listPrompts(apiKeyStore).then(data => {
        setApiKeyPrompts(Array.isArray(data.prompts) ? data.prompts : []);
      }).catch(() => setApiKeyPrompts([]));
    } else {
      setApiKeyPrompts([]);
    }
    setApiKeyPromptIndex('');
  }, [apiKeyStore]);

  // === Prompt handlers ===
  const loadPrompts = async () => {
    if (!currentStore) return;
    setLoading(true);
    try {
      const data = await api.listPrompts(currentStore);
      setPrompts(data.prompts || []);
      setActivePromptId(data.active_prompt_id);
      setMaxPrompts(data.max_prompts || 3);
    } catch (e) {
      console.error('Failed to load prompts:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!currentStore || !newPromptContent.trim()) return;
    setCreating(true);
    try {
      const name = newPromptName.trim() || `Prompt ${prompts.length + 1}`;
      await api.createPrompt(currentStore, name, newPromptContent.trim());
      setNewPromptName('');
      setNewPromptContent('');
      await loadPrompts();
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      alert('建立失敗: ' + errorMsg);
    } finally {
      setCreating(false);
    }
  };

  const handleSetActive = async (promptId: string | null) => {
    if (!currentStore) return;
    try {
      await api.setActivePrompt(currentStore, promptId);
      await loadPrompts();
      await onRestartChat();
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      alert('設定失敗: ' + errorMsg);
    }
  };

  const handleDelete = async (promptId: string) => {
    if (!currentStore) return;
    if (!confirm('確定要刪除此 Prompt 嗎？')) return;
    try {
      await api.deletePrompt(currentStore, promptId);
      await loadPrompts();
      if (promptId === activePromptId) await onRestartChat();
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      alert('刪除失敗: ' + errorMsg);
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

  const handleEscape = useCallback(() => {
    if (editingId) cancelEdit();
    else onClose();
  }, [editingId, onClose]);
  useEscapeKey(handleEscape, isOpen);

  const toggleExpand = (promptId: string) => {
    setExpandedIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(promptId)) newSet.delete(promptId);
      else newSet.add(promptId);
      return newSet;
    });
  };

  const saveEdit = async () => {
    if (!currentStore || !editingId) return;
    try {
      await api.updatePrompt(currentStore, editingId, editName, editContent);
      await loadPrompts();
      if (editingId === activePromptId) await onRestartChat();
      cancelEdit();
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      alert('更新失敗: ' + errorMsg);
    }
  };

  const handleModelChange = async (modelId: string) => {
    setSelectedModel(modelId);
    localStorage.setItem('selectedModel', modelId);
    await onRestartChat();
  };

  // === API Key handlers ===
  const loadApiKeys = async () => {
    setApiKeysLoading(true);
    try {
      const data = await api.listApiKeys(apiKeyStore || undefined);
      setApiKeys(data);
    } catch (e) {
      console.error('Failed to load API keys:', e);
    } finally {
      setApiKeysLoading(false);
    }
  };

  const handleCreateApiKey = async () => {
    if (!apiKeyStore || !apiKeyName.trim()) return;
    setApiKeyCreating(true);
    try {
      const promptIndex = apiKeyPromptIndex !== '' ? Number(apiKeyPromptIndex) : null;
      const result = await api.createApiKey(apiKeyName.trim(), apiKeyStore, promptIndex);
      setNewApiKeyCreated(result.key);
      setApiKeyName('');
      setApiKeyPromptIndex('');
      await loadApiKeys();
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      alert('建立失敗: ' + errorMsg);
    } finally {
      setApiKeyCreating(false);
    }
  };

  const handleDeleteApiKey = async (keyId: string) => {
    if (!confirm('確定要刪除此 API Key 嗎？')) return;
    try {
      await api.deleteServerApiKey(keyId);
      await loadApiKeys();
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      alert('刪除失敗: ' + errorMsg);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal app-container prompt-management-modal" onClick={e => e.stopPropagation()} style={{ maxWidth: '700px' }}>
        <h2>⚙ 設置</h2>

        <div className="prompt-modal-tabs">
          {[
            { key: 'model' as const, label: '🤖 模型' },
            { key: 'prompt' as const, label: '📝 Prompt' },
            { key: 'apikey' as const, label: '🔑 API 金鑰' },
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`prompt-modal-tab-btn ${activeTab === tab.key ? 'active' : ''} ${tab.key}`}
              type="button"
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        {activeTab === 'model' && (
          <ModelSelectionTab
            selectedModel={selectedModel}
            onModelChange={handleModelChange}
          />
        )}

        {activeTab === 'prompt' && (
          <PromptTab
            currentStore={currentStore}
            prompts={prompts}
            activePromptId={activePromptId}
            maxPrompts={maxPrompts}
            loading={loading}
            editingId={editingId}
            editName={editName}
            editContent={editContent}
            expandedIds={expandedIds}
            newPromptName={newPromptName}
            newPromptContent={newPromptContent}
            creating={creating}
            onCreatePrompt={handleCreate}
            onSetActive={handleSetActive}
            onDelete={handleDelete}
            onStartEdit={startEdit}
            onCancelEdit={cancelEdit}
            onSaveEdit={saveEdit}
            onToggleExpand={toggleExpand}
            onNewPromptNameChange={setNewPromptName}
            onNewPromptContentChange={setNewPromptContent}
            onEditNameChange={setEditName}
            onEditContentChange={setEditContent}
          />
        )}

        {activeTab === 'apikey' && (
          <ApiKeyTab
            stores={stores}
            apiKeyStore={apiKeyStore}
            apiKeyName={apiKeyName}
            apiKeyPromptIndex={apiKeyPromptIndex}
            apiKeyPrompts={apiKeyPrompts}
            apiKeys={apiKeys}
            apiKeysLoading={apiKeysLoading}
            apiKeyCreating={apiKeyCreating}
            newApiKeyCreated={newApiKeyCreated}
            onApiKeyStoreChange={setApiKeyStore}
            onApiKeyNameChange={setApiKeyName}
            onApiKeyPromptIndexChange={setApiKeyPromptIndex}
            onCreateApiKey={handleCreateApiKey}
            onDeleteApiKey={handleDeleteApiKey}
            onDismissNewKey={() => setNewApiKeyCreated(null)}
          />
        )}

        <div className="modal-actions">
          <button onClick={onClose} className="secondary">
            關閉
          </button>
        </div>
      </div>
    </div>
  );
}
