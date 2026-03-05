import { useState, useEffect, useCallback, useRef } from 'react';
import { useTheme } from './useTheme';
import * as api from '../services/api';
import type {
  Store,
  FileItem,
  Message,
  KnowledgeTarget,
  CmsAppTarget,
  KnowledgeLanguage,
} from '../types';

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function normalizeKeyLabels(keyNames: unknown): string[] {
  if (!Array.isArray(keyNames)) return [];
  return keyNames.map((keyName, index) => {
    if (typeof keyName === 'string') {
      const trimmed = keyName.trim();
      return trimmed || `Key #${index + 1}`;
    }
    if (keyName && typeof keyName === 'object') {
      const candidate = [keyName.name, keyName.label, keyName.display_name]
        .find((value): value is string => typeof value === 'string' && value.trim().length > 0);
      if (candidate) {
        return candidate.trim();
      }
    }
    return `Key #${index + 1}`;
  });
}

function buildKnowledgeTargets(storeList: Store[]): KnowledgeTarget[] {
  return storeList.map((store) => ({
    id: store.name,
    kind: 'store' as const,
    label: store.display_name || store.name,
    storeName: store.name,
    managedApp: store.managed_app,
    managedLanguage: store.managed_language,
  }));
}

function findKnowledgeTarget(targetId: string | null, storeList: Store[]): KnowledgeTarget | null {
  if (!targetId) return null;
  return buildKnowledgeTargets(storeList).find((target) => target.id === targetId) || null;
}

function getManagedKnowledgeContext(target: KnowledgeTarget | null): {
  appTarget: CmsAppTarget;
  language: KnowledgeLanguage;
} | null {
  if (!target || target.kind !== 'store' || !target.managedApp || !target.managedLanguage) return null;
  return {
    appTarget: target.managedApp,
    language: target.managedLanguage,
  };
}

function getProjectFilterOptions(storeList: Store[], keyNames: string[]): Array<{ value: string; label: string }> {
  if (keyNames.length <= 1) return [];
  return [
    { value: 'all', label: '全部專案' },
    ...keyNames.map((name, i) => ({
      value: `key:${i}`,
      label: name || `Key #${i + 1}`,
    })),
  ];
}

function filterStoresByProject(storeList: Store[], projectFilter: string): Store[] {
  if (projectFilter === 'all') return storeList;
  const [, keyIndexText] = projectFilter.split(':');
  const keyIndex = Number(keyIndexText);
  if (Number.isNaN(keyIndex)) return storeList;
  return storeList.filter((store) => (store.key_index ?? 0) === keyIndex);
}

async function fetchFilesForTarget(target: KnowledgeTarget): Promise<FileItem[]> {
  if (target.kind !== 'store') {
    return [];
  }
  const managedContext = getManagedKnowledgeContext(target);
  const files: FileItem[] = managedContext
    ? ((await api.listManagedKnowledgeFiles(managedContext.appTarget, managedContext.language)).files || []) as FileItem[]
    : await api.fetchFiles(target.storeName);

  files.sort((a, b) => (a.display_name || a.name).localeCompare(b.display_name || b.name));
  return files;
}

export function useAppChat() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [storeModalOpen, setStoreModalOpen] = useState(false);
  const [promptModalOpen, setPromptModalOpen] = useState(false);
  const [userApiKeyModalOpen, setUserApiKeyModalOpen] = useState(false);
  const [conversationHistoryModalOpen, setConversationHistoryModalOpen] = useState(false);
  const [status, setStatus] = useState('');
  const [stores, setStores] = useState<Store[]>([]);
  const [keyNames, setKeyNames] = useState<string[]>([]);
  const [projectFilter, setProjectFilter] = useState(
    () => localStorage.getItem('projectFilter') || 'all'
  );

  useEffect(() => {
    localStorage.setItem('projectFilter', projectFilter);
  }, [projectFilter]);
  const [currentTargetId, setCurrentTargetId] = useState<string | null>(null);
  const [files, setFiles] = useState<FileItem[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const { theme, toggleTheme } = useTheme();
  const currentTargetIdRef = useRef<string | null>(null);
  const filesRequestIdRef = useRef(0);

  const projectFilterOptions = getProjectFilterOptions(stores, keyNames);
  const filteredStores = filterStoresByProject(stores, projectFilter);
  const knowledgeTargets = buildKnowledgeTargets(filteredStores);
  const currentTarget = findKnowledgeTarget(currentTargetId, filteredStores);
  const currentStore = currentTarget?.kind === 'store' ? currentTarget.storeName : null;
  const managedContext = getManagedKnowledgeContext(currentTarget);
  const isManagedStore = managedContext !== null;

  const clearSelection = (includeChatState: boolean = false): void => {
    setCurrentTargetId(null);
    currentTargetIdRef.current = null;
    filesRequestIdRef.current += 1;
    setFiles([]);
    setFilesLoading(false);
    if (includeChatState) {
      setMessages([]);
      setSessionId(null);
    }
  };

  const toggleSidebar = () => setSidebarOpen(!sidebarOpen);

  const showStatus = (msg: string) => {
    setStatus(msg);
    setTimeout(() => setStatus(''), 3000);
  };

  const refreshStores = useCallback(async () => {
    try {
      const [data, keyInfo] = await Promise.all([
        api.fetchStores(),
        api.getKeyInfos().catch(() => ({ count: 0, names: [] })),
      ]);
      setStores(data);
      setKeyNames(normalizeKeyLabels(keyInfo.names));
      return data;
    } catch (e) {
      showStatus('載入知識庫列表失敗');
      console.error(e);
      return [];
    }
  }, []);

  const refreshFiles = useCallback(async (targetOverride?: KnowledgeTarget | null) => {
    const target = targetOverride ?? findKnowledgeTarget(currentTargetId, stores);
    if (!target) {
      filesRequestIdRef.current += 1;
      setFiles([]);
      setFilesLoading(false);
      return;
    }

    const requestId = filesRequestIdRef.current + 1;
    filesRequestIdRef.current = requestId;
    setFilesLoading(true);
    try {
      const nextFiles = await fetchFilesForTarget(target);
      if (filesRequestIdRef.current !== requestId) return;
      if (currentTargetIdRef.current !== target.id) return;
      setFiles(nextFiles);
    } catch (e) {
      if (filesRequestIdRef.current !== requestId) return;
      if (currentTargetIdRef.current !== target.id) return;
      console.error('Failed to fetch files:', e);
      setFiles([]);
    } finally {
      if (filesRequestIdRef.current === requestId) {
        setFilesLoading(false);
      }
    }
  }, [currentTargetId, stores]);

  const handleStoreChange = async (targetId: string, storeListOverride?: Store[]) => {
    const resolvedStores = storeListOverride ?? stores;
    const target = findKnowledgeTarget(targetId, resolvedStores);
    if (!target) return;
    if (target.kind !== 'store') return;

    setCurrentTargetId(target.id);
    currentTargetIdRef.current = target.id;
    filesRequestIdRef.current += 1;
    setFiles([]);
    setFilesLoading(true);
    setMessages([]);
    setSessionId(null);
    localStorage.setItem('lastKnowledgeTargetId', target.id);

    const nextManagedContext = getManagedKnowledgeContext(target);
    if (nextManagedContext) {
      showStatus(`已切換到 ${nextManagedContext.appTarget.toUpperCase()} ${nextManagedContext.language === 'zh' ? '中文' : 'English'} 知識庫`);
    }

    localStorage.setItem('lastStore', target.storeName);
    try {
      const result = await api.startChat(target.storeName);
      if (result.prompt_applied) {
        showStatus('✅ 已套用自訂 Prompt');
      }
      if (result.session_id) {
        setSessionId(result.session_id);
      }
    } catch (e) {
      const errorMsg = toErrorMessage(e);
      showStatus('連線失敗: ' + errorMsg);
      setMessages([
        {
          role: 'model',
          text: '連線失敗: ' + errorMsg,
          error: true,
        },
      ]);
    }
  };

  const handleRefreshKnowledge = useCallback(async () => {
    const nextStores = await refreshStores();
    const nextFilteredStores = filterStoresByProject(nextStores, projectFilter);
    const nextTarget = findKnowledgeTarget(currentTargetId, nextFilteredStores);
    if (nextTarget) {
      await refreshFiles(nextTarget);
      return;
    }
    const fallbackTarget = buildKnowledgeTargets(nextFilteredStores)[0] || null;
    if (fallbackTarget) {
      await handleStoreChange(fallbackTarget.id, nextFilteredStores);
      await refreshFiles(fallbackTarget);
      return;
    }
    clearSelection();
  }, [currentTargetId, projectFilter, refreshFiles, refreshStores, stores]);

  useEffect(() => {
    const init = async () => {
      const storeList = await refreshStores();
      const targets = buildKnowledgeTargets(filterStoresByProject(storeList, projectFilter));
      const lastTargetId = localStorage.getItem('lastKnowledgeTargetId') || localStorage.getItem('lastStore');
      if (lastTargetId && targets.some((target) => target.id === lastTargetId)) {
        await handleStoreChange(lastTargetId, filterStoresByProject(storeList, projectFilter));
        return;
      }
      if (targets.length > 0) {
        await handleStoreChange(targets[0].id, filterStoresByProject(storeList, projectFilter));
      }
    };
    void init();
  }, [projectFilter, refreshStores]);

  useEffect(() => {
    currentTargetIdRef.current = currentTargetId;
  }, [currentTargetId]);

  useEffect(() => {
    const nextTargets = buildKnowledgeTargets(filteredStores);
    if (currentTargetId && nextTargets.some((target) => target.id === currentTargetId)) {
      return;
    }
    if (nextTargets.length > 0) {
      void handleStoreChange(nextTargets[0].id, filteredStores);
      return;
    }
    clearSelection(true);
  }, [projectFilter, stores]);

  useEffect(() => {
    if (currentTarget) {
      void refreshFiles(currentTarget);
    }
  }, [currentTargetId, stores]);

  const handleRestartChat = async () => {
    if (!currentStore) return;
    if (messages.length > 0 && !window.confirm('確定要重新開始對話嗎？')) return;
    setMessages([]);
    try {
      const result = await api.startChat(currentStore, sessionId);
      if (result.session_id) {
        setSessionId(result.session_id);
      }
      if (result.prompt_applied) {
        showStatus('✅ 已套用新的 Prompt');
      }
    } catch (e) {
      showStatus('重新啟動失敗: ' + toErrorMessage(e));
    }
  };

  const handleCreateStore = async (name: string, keyIndex: number = 0) => {
    try {
      const newStore = await api.createStore(name, keyIndex);
      const nextStores = await refreshStores();
      await handleStoreChange(newStore.name, nextStores);
    } catch (e) {
      alert('建立失敗: ' + toErrorMessage(e));
    }
  };

  const handleDeleteStore = async (storeName: string) => {
    if (!storeName) return;
    try {
      await api.deleteStore(storeName);
      const nextStores = await refreshStores();
      const nextFilteredStores = filterStoresByProject(nextStores, projectFilter);
      if (currentStore === storeName) {
        const fallbackTarget = buildKnowledgeTargets(nextFilteredStores)[0] || null;
        if (fallbackTarget) {
          await handleStoreChange(fallbackTarget.id, nextFilteredStores);
        } else {
          clearSelection(true);
        }
      }
      showStatus('知識庫已刪除');
    } catch (e) {
      alert('刪除失敗: ' + toErrorMessage(e));
    }
  };

  const handleUploadFile = async (file: File) => {
    if (!currentTarget) {
      alert('請先選擇知識庫');
      return;
    }
    try {
      if (managedContext) {
        await api.uploadManagedKnowledgeFile(managedContext.appTarget, managedContext.language, file);
      } else if (currentTarget.kind === 'store') {
        await api.uploadFile(currentTarget.storeName, file);
      }
      await refreshFiles(currentTarget);
      showStatus('文件上傳成功');
    } catch (e) {
      alert('上傳失敗: ' + toErrorMessage(e));
    }
  };

  const handleDeleteFile = async (fileName: string) => {
    if (!currentTarget || !confirm('確定刪除此文件？')) return;
    try {
      if (managedContext) {
        await api.deleteManagedKnowledgeFile(managedContext.appTarget, fileName, managedContext.language);
      } else if (currentTarget.kind === 'store') {
        await api.deleteFile(fileName);
      }
      await refreshFiles(currentTarget);
      showStatus('文件已刪除');
    } catch (e) {
      alert('刪除失敗: ' + toErrorMessage(e));
    }
  };

  const handleSendMessage = async (text: string) => {
    if (!currentStore) return;
    setMessages((prev) => [
      ...prev,
      { role: 'user', text },
      { role: 'model', loading: true },
    ]);
    setLoading(true);

    try {
      let activeSessionId = sessionId;

      if (!activeSessionId) {
        const startResult = await api.startChat(currentStore);
        if (startResult.session_id) {
          activeSessionId = startResult.session_id;
          setSessionId(startResult.session_id);
        }
      }

      const data = await api.sendMessage(text, activeSessionId || undefined);
      setMessages((prev) => {
        const newMessages = [...prev];
        newMessages[newMessages.length - 2] = {
          ...newMessages[newMessages.length - 2],
          turnNumber: data.turn_number,
        };
        newMessages[newMessages.length - 1] = {
          role: 'model',
          text: data.answer,
          turnNumber: data.turn_number,
        };
        return newMessages;
      });
    } catch (e) {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = { role: 'model', text: '錯誤: ' + toErrorMessage(e), error: true };
        return updated;
      });
    } finally {
      setLoading(false);
    }
  };

  const handleRegenerate = async (turnNumber: number) => {
    if (!sessionId || loading || !currentStore) return;

    const userMsg = messages.find((message) => message.role === 'user' && message.turnNumber === turnNumber);
    if (!userMsg?.text) return;

    setMessages((prev) => {
      const userIdx = prev.findIndex((message) => message.role === 'user' && message.turnNumber === turnNumber);
      if (userIdx === -1) return prev;
      const truncated = prev.slice(0, userIdx + 1);
      return [...truncated, { role: 'model', loading: true }];
    });
    setLoading(true);

    try {
      const data = await api.sendMessage(userMsg.text, sessionId, turnNumber);
      setMessages((prev) => {
        const newMessages = [...prev];
        newMessages[newMessages.length - 1] = {
          role: 'model',
          text: data.answer,
          turnNumber: data.turn_number,
        };
        return newMessages;
      });
    } catch (e) {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = { role: 'model', text: '錯誤: ' + toErrorMessage(e), error: true };
        return updated;
      });
    } finally {
      setLoading(false);
    }
  };

  const handleEditAndResend = async (turnNumber: number, newText: string) => {
    if (!sessionId || loading || !currentStore) return;

    setMessages((prev) => {
      const userIdx = prev.findIndex((message) => message.role === 'user' && message.turnNumber === turnNumber);
      if (userIdx === -1) return prev;
      const truncated = prev.slice(0, userIdx);
      return [...truncated, { role: 'user', text: newText }, { role: 'model', loading: true }];
    });
    setLoading(true);

    try {
      const data = await api.sendMessage(newText, sessionId, turnNumber);
      setMessages((prev) => {
        const newMessages = [...prev];
        newMessages[newMessages.length - 2] = {
          ...newMessages[newMessages.length - 2],
          turnNumber: data.turn_number,
        };
        newMessages[newMessages.length - 1] = {
          role: 'model',
          text: data.answer,
          turnNumber: data.turn_number,
        };
        return newMessages;
      });
    } catch (e) {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = { role: 'model', text: '錯誤: ' + toErrorMessage(e), error: true };
        return updated;
      });
    } finally {
      setLoading(false);
    }
  };

  return {
    sidebarOpen,
    storeModalOpen, setStoreModalOpen,
    promptModalOpen, setPromptModalOpen,
    userApiKeyModalOpen, setUserApiKeyModalOpen,
    conversationHistoryModalOpen, setConversationHistoryModalOpen,
    status,
    stores,
    projectFilter,
    projectFilterOptions,
    knowledgeTargets,
    currentTarget,
    currentTargetId,
    currentStore,
    managedContext,
    files,
    filesLoading,
    messages, setMessages,
    loading,
    sessionId, setSessionId,
    isManagedStore,
    theme, toggleTheme,
    toggleSidebar,
    showStatus,
    refreshStores,
    refreshFiles,
    handleRefreshKnowledge,
    setProjectFilter,
    handleStoreChange,
    handleRestartChat,
    handleCreateStore,
    handleDeleteStore,
    handleUploadFile,
    handleDeleteFile,
    handleSendMessage,
    handleRegenerate,
    handleEditAndResend,
  };
}
