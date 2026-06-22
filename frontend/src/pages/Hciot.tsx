import { useCallback, useEffect, useMemo, useRef, useState, type RefObject, type SetStateAction } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, BookOpen, ChevronDown, ExternalLink, FileText, HeartPulse, History, Loader, LogOut, Menu, Moon, RotateCcw, Settings, Sun, Volume2 } from 'lucide-react';
import { fetchWithApiKey } from '../services/api';

import HciotSelect from '../components/hciot/HciotSelect';
import ConversationHistoryModal from '../components/ConversationHistoryModal';
import HciotSettingsModal from '../components/HciotSettingsModal';
import HciotInputArea from '../components/hciot/HciotInputArea';
import HciotKnowledgeWorkspace from '../components/hciot/HciotKnowledgeWorkspace';
import HciotMessageList, { type HciotMessage } from '../components/hciot/HciotMessageList';
import HciotTopicGrid from '../components/hciot/HciotTopicGrid';
import {
  HCIOT_DEFAULT_STORE_NAME,
  normalizeHciotLanguage,
  type HciotCategory,
  type HciotTopic,
} from '../config/hciotTopics';
import { useAutoResize } from '../hooks/useAutoResize';
import { useCurrentUserProfile } from '../hooks/useCurrentUserProfile';
import { useEnterToSubmit } from '../hooks/useEnterToSubmit';
import { useFocusOnOpen } from '../hooks/useFocusOnOpen';
import { useLogoutRedirect } from '../hooks/useLogoutRedirect';
import { useScrollToBottom } from '../hooks/useScrollToBottom';
import { useTheme } from '../hooks/useTheme';
import { isAdminRole, isSuperAdmin } from '../utils/authRouting';
import DbSyncButton from '../components/DbSyncButton';
import * as api from '../services/api';
import type { TtsState } from '../types';
import '../styles/shared/index.css';
import '../styles/shared/animations.css';
import '../styles/shared/settings.css';
import '../styles/qaWorkspace/layout.css';
import '../styles/qaWorkspace/components.css';
import '../styles/hciot/components-chat.css';
import '../styles/qaWorkspace/components-topic.css';
import '../styles/qaWorkspace/workspace.css';
import '../styles/qaWorkspace/workspace-upload.css';
import '../styles/qaWorkspace/workspace-upload-images.css';
import '../styles/qaWorkspace/workspace-upload-enhancements.css';
import '../styles/qaWorkspace/workspace-upload-preview.css';
import '../styles/qaWorkspace/workspace-upload-edit.css';
import '../styles/qaWorkspace/workspace-table.css';
import '../styles/qaWorkspace/workspace-images.css';

const TTS_MAX_ATTEMPTS = 16;
const TTS_POLL_INTERVAL_MS = 3000;
const TTS_STALL_TIMEOUT_MS = 12000;
const TTS_CHARACTER_STORAGE_KEY = 'hciot:tts-character';
const WORKSPACE_STORAGE_KEY = 'hciot:workspace';
const SELECTED_CATEGORY_STORAGE_KEY = 'hciot:selected-category';
const SELECTED_TOPIC_STORAGE_KEY = 'hciot:selected-topic';
const HCIOT_EXTERNAL_LINK_URL =
  (import.meta.env.VITE_HCIOT_EXTERNAL_LINK_URL as string | undefined)?.trim() || '';
const HCIOT_EXTERNAL_LINK_LABEL = '語音管理';
const HCIOT_MANUAL_URL = `${import.meta.env.BASE_URL}hciot-manual.html`;
const HCIOT_MANUAL_LABEL = '操作手冊';
const HCIOT_UI_TEXT = {
  appTitle: 'HCIoT 衛教助理',
  brandKicker: 'Hospital Education Interface',
  statusReady: '準備中...',
  statusConnected: '已連線',
  statusFailed: '連線失敗',
  statusChatting: '對話中',
  loading: '載入中...',
  restartConfirm: '確定要重新開始對話嗎？所有記錄將清除。',
  languageConfirm: '切換語言會重新開始對話，確定要繼續嗎？',
  networkError: '網路錯誤，請稍後再試',
  inputPlaceholder: '請輸入想詢問的症狀、照護方式、回診時機或飲食建議...',
  settingsTitle: '人物設定',
  restartTitle: '重新開始',
  historyTitle: '查看對話歷史',
  languageTitle: '切換語言',
  themeTitle: '切換主題',
  topicsLoadError: '無法載入題目分類，請稍後再試。',
};
type WorkspaceMode = 'chat' | 'files';
interface TopicSelection {
  categoryId: string | null;
  topicId: string | null;
}

const EMPTY_TOPIC_SELECTION: TopicSelection = { categoryId: null, topicId: null };

function resolveTopicSelection(
  categories: HciotCategory[],
  current: TopicSelection,
): TopicSelection {
  if (!categories.length) {
    return EMPTY_TOPIC_SELECTION;
  }

  const hasSavedCategory = localStorage.getItem(SELECTED_CATEGORY_STORAGE_KEY) !== null;

  const categoryId = current.categoryId;
  const topicId = current.topicId;

  let matchedTopic: HciotTopic | null = null;
  let matchedCategory: HciotCategory | null = null;

  if (topicId) {
    for (const cat of categories) {
      const found = cat.topics.find((t) => t.id === topicId);
      if (found) {
        matchedTopic = found;
        matchedCategory = cat;
        break;
      }
    }
  }

  if (matchedTopic && matchedCategory) {
    return {
      categoryId: categoryId === null && hasSavedCategory ? null : matchedCategory.id,
      topicId: topicId,
    };
  }

  if (categoryId === null && hasSavedCategory) {
    const allTopics = categories.flatMap((cat) => cat.topics);
    const defaultTopicId = allTopics[0]?.id || null;
    return { categoryId: null, topicId: defaultTopicId };
  }

  const category = categories.find((cat) => cat.id === categoryId) || categories[0];
  const defaultTopicId = category.topics[0]?.id || null;
  return { categoryId: category.id, topicId: defaultTopicId };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function normalizeTtsMessageId(ttsMessageId?: string): string {
  return (ttsMessageId || '').trim();
}

function readStoredTtsCharacter(): string {
  return localStorage.getItem(TTS_CHARACTER_STORAGE_KEY) || '';
}

function writeStoredTtsCharacter(value: string): void {
  if (value) {
    localStorage.setItem(TTS_CHARACTER_STORAGE_KEY, value);
    return;
  }

  localStorage.removeItem(TTS_CHARACTER_STORAGE_KEY);
}

function resolveTtsCharacter(characters: string[], preferredValue?: string): string {
  const nextValue = (preferredValue || readStoredTtsCharacter()).trim();
  if (characters.includes(nextValue)) {
    return nextValue;
  }

  return characters[0] || '';
}

function readStoredWorkspace(): WorkspaceMode {
  return sessionStorage.getItem(WORKSPACE_STORAGE_KEY) === 'files' ? 'files' : 'chat';
}

function writeStoredWorkspace(workspace: WorkspaceMode): void {
  sessionStorage.setItem(WORKSPACE_STORAGE_KEY, workspace);
}

function buildSessionInfo(sessionId?: string | null): string {
  return sessionId ? `#${sessionId.substring(0, 8)}` : '';
}

function focusSoon(ref: RefObject<HTMLTextAreaElement | null>): void {
  window.setTimeout(() => ref.current?.focus(), 100);
}

function isSameMessage(left: HciotMessage, right: HciotMessage): boolean {
  return (
    left.timestamp === right.timestamp &&
    left.type === right.type &&
    left.turnNumber === right.turnNumber &&
    left.text === right.text
  );
}

function attachTtsMessageId(
  messages: HciotMessage[],
  targetMessage: HciotMessage,
  ttsMessageId: string,
): HciotMessage[] {
  let matched = false;

  return messages.map((item) => {
    if (matched || !isSameMessage(item, targetMessage)) {
      return item;
    }

    matched = true;
    return { ...item, ttsMessageId };
  });
}

function buildOpeningMessages(openingMessage?: string): HciotMessage[] {
  if (!openingMessage) {
    return [];
  }

  return [{ text: openingMessage, type: 'assistant', timestamp: Date.now() }];
}

function getTopicDisabledMessage(storeMissing: boolean, topicsError: boolean): string | null {
  if (storeMissing) {
    return `找不到知識庫 ${HCIOT_DEFAULT_STORE_NAME}，請先建立 store 並匯入衛教文件。`;
  }

  if (topicsError) {
    return HCIOT_UI_TEXT.topicsLoadError;
  }

  return null;
}

function findUserMessageIndexByTurn(messages: HciotMessage[], turnNumber: number): number {
  return messages.findIndex(
    (message) => message.type === 'user' && message.turnNumber === turnNumber,
  );
}

function updateLastUserTurnNumber(
  messages: HciotMessage[],
  turnNumber?: number,
): HciotMessage[] {
  if (turnNumber === undefined) {
    return messages;
  }

  let lastUserIndex = -1;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].type === 'user') {
      lastUserIndex = index;
      break;
    }
  }

  if (lastUserIndex === -1) {
    return messages;
  }

  return messages.map((message, index) => (
    index === lastUserIndex ? { ...message, turnNumber } : message
  ));
}

export default function Hciot() {
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();
  const logProfileError = useCallback((error: unknown) => {
    console.error('Hciot failed to load profile on mount:', error);
  }, []);
  const logLogoutError = useCallback((error: unknown) => {
    console.error('Logout failed:', error);
  }, []);
  const { profile } = useCurrentUserProfile({ onError: logProfileError });
  const handleLogoutClick = useLogoutRedirect(undefined, logLogoutError);

  const [storeName, setStoreName] = useState<string | null>(null);
  const [storeMissing, setStoreMissing] = useState(false);
  const [topicsError, setTopicsError] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<HciotMessage[]>([]);
  const [userInput, setUserInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [statusText, setStatusText] = useState(HCIOT_UI_TEXT.statusReady);
  const [sessionInfo, setSessionInfo] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [currentLanguage, setCurrentLanguage] = useState(() =>
    normalizeHciotLanguage(localStorage.getItem('language') || 'zh'),
  );
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [workspace, setWorkspace] = useState<WorkspaceMode>(() => readStoredWorkspace());
  const [editingTurn, setEditingTurn] = useState<number | null>(null);
  const [editText, setEditText] = useState('');
  const [topicSelection, setTopicSelection] = useState<TopicSelection>(() => {
    const savedCat = localStorage.getItem(SELECTED_CATEGORY_STORAGE_KEY);
    const savedTopic = localStorage.getItem(SELECTED_TOPIC_STORAGE_KEY);
    return {
      categoryId: savedCat === '__all__' ? null : (savedCat || null),
      topicId: savedTopic,
    };
  });
  const [categories, setCategories] = useState<HciotCategory[]>([]);
  const [ttsStateMap, setTtsStateMap] = useState<Record<string, TtsState>>({});
  const [ttsCharacters, setTtsCharacters] = useState<string[]>([]);
  const [selectedTtsCharacter, setSelectedTtsCharacter] = useState<string>(
    () => readStoredTtsCharacter(),
  );
  const [activeTtsMessageId, setActiveTtsMessageId] = useState<string | null>(null);
  const [previewingVoice, setPreviewingVoice] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [showToolsMenu, setShowToolsMenu] = useState(false);

  const selectedCategoryId = topicSelection.categoryId;
  const selectedTopicId = topicSelection.topicId;
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const editTextareaRef = useRef<HTMLTextAreaElement>(null);
  const ttsAudioUrlMapRef = useRef<Map<string, string>>(new Map());
  const ttsPendingMapRef = useRef<Map<string, Promise<void>>>(new Map());
  const ttsPendingSinceRef = useRef<Map<string, number>>(new Map());
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const isUnmountedRef = useRef(false);
  const ttsEpochRef = useRef(0);
  const toolsMenuRef = useRef<HTMLDivElement | null>(null);

  useScrollToBottom(messagesEndRef, [messages]);
  useAutoResize(inputRef, userInput);

  useEffect(() => {
    isUnmountedRef.current = false;
    return () => { isUnmountedRef.current = true; };
  }, []);

  useEffect(() => {
    if (!showToolsMenu) return;

    const closeWhenOutside = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (toolsMenuRef.current?.contains(target)) return;
      if (target instanceof Element && target.closest('.app-select-content')) return;
      setShowToolsMenu(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setShowToolsMenu(false);
    };

    document.addEventListener('pointerdown', closeWhenOutside);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('pointerdown', closeWhenOutside);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [showToolsMenu]);

  useEffect(() => {
    if (topicSelection.categoryId !== null) {
      localStorage.setItem(SELECTED_CATEGORY_STORAGE_KEY, topicSelection.categoryId);
    } else {
      localStorage.setItem(SELECTED_CATEGORY_STORAGE_KEY, '__all__');
    }
    if (topicSelection.topicId !== null) {
      localStorage.setItem(SELECTED_TOPIC_STORAGE_KEY, topicSelection.topicId);
    } else {
      localStorage.removeItem(SELECTED_TOPIC_STORAGE_KEY);
    }
  }, [topicSelection]);

  const setSelectedTopicId = useCallback((next: SetStateAction<string | null>) => {
    setTopicSelection((current) => ({
      ...current,
      topicId: typeof next === 'function' ? next(current.topicId) : next,
    }));
  }, []);

  useEffect(() => {
    const loadTtsCharacters = async () => {
      try {
        const data = await api.getHciotTtsCharacters();
        const availableCharacters = data.characters ?? [];
        setTtsCharacters(availableCharacters);
        setSelectedTtsCharacter((currentValue) => {
          const nextValue = resolveTtsCharacter(availableCharacters, currentValue);
          writeStoredTtsCharacter(nextValue);
          return nextValue;
        });
      } catch (error) {
        console.error('Failed to load HCIoT TTS characters:', error);
        setTtsCharacters([]);
      }
    };

    void loadTtsCharacters();
  }, []);

  useEffect(() => {
    writeStoredTtsCharacter(selectedTtsCharacter);
  }, [selectedTtsCharacter]);

  const setTtsState = useCallback((id: string, state: TtsState) => {
    setTtsStateMap((prev) => ({ ...prev, [id]: state }));
  }, []);

  const markTtsError = useCallback((id: string) => {
    ttsPendingSinceRef.current.delete(id);
    setTtsState(id, 'error');
  }, [setTtsState]);

  const isStaleEpoch = useCallback(
    (startEpoch: number) => isUnmountedRef.current || ttsEpochRef.current !== startEpoch,
    [],
  );

  const warmupTtsAudio = useCallback((ttsMessageId?: string, force = false) => {
    const id = normalizeTtsMessageId(ttsMessageId);
    if (!id || ttsAudioUrlMapRef.current.has(id)) return;
    if (ttsPendingMapRef.current.has(id) && !force) return;
    if (force) ttsPendingMapRef.current.delete(id);
    const startEpoch = ttsEpochRef.current;

    const task = (async () => {
      setTtsState(id, 'pending');
      ttsPendingSinceRef.current.set(id, Date.now());
      try {
        for (let attempt = 0; attempt < TTS_MAX_ATTEMPTS; attempt += 1) {
          if (isStaleEpoch(startEpoch)) return;
          const res = await fetchWithApiKey(`/api/hciot/tts/${encodeURIComponent(id)}`);
          if (res.status === 202) {
            await sleep(Math.min(350 + attempt * 80, 1200));
            continue;
          }
          if (res.status === 404) {
            markTtsError(id);
            return;
          }
          if (!res.ok) throw new Error(await res.text());
          const blob = await res.blob();
          const audioUrl = URL.createObjectURL(blob);
          if (isStaleEpoch(startEpoch)) {
            URL.revokeObjectURL(audioUrl);
            return;
          }
          const oldUrl = ttsAudioUrlMapRef.current.get(id);
          if (oldUrl) URL.revokeObjectURL(oldUrl);
          ttsAudioUrlMapRef.current.set(id, audioUrl);
          ttsPendingSinceRef.current.delete(id);
          setTtsState(id, 'ready');
          return;
        }
        markTtsError(id);
      } catch {
        if (!isStaleEpoch(startEpoch)) markTtsError(id);
      }
    })().finally(() => {
      ttsPendingMapRef.current.delete(id);
    });
    ttsPendingMapRef.current.set(id, task);
  }, [isStaleEpoch, markTtsError, setTtsState]);

  const playAssistantTts = useCallback(async (msg: HciotMessage) => {
    let ttsMessageId = normalizeTtsMessageId(msg.ttsMessageId);
    if (ttsMessageId && activeTtsMessageId === ttsMessageId) {
      currentAudioRef.current?.pause();
      setActiveTtsMessageId(null);
      return;
    }

    setPreviewingVoice(false);

    if (!ttsMessageId) {
      const sourceText = (msg.ttsText || msg.text || '').trim();
      if (!sourceText) return;
      const createRes = await fetchWithApiKey('/api/hciot/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: sourceText,
          language: currentLanguage,
          character: selectedTtsCharacter || undefined,
        }),
      });
      if (!createRes.ok) return;
      const createData = await createRes.json();
      ttsMessageId = normalizeTtsMessageId(String(createData?.tts_message_id || ''));
      if (!ttsMessageId) return;
      setMessages((prev) => attachTtsMessageId(prev, msg, ttsMessageId));
    }

    if (activeTtsMessageId === ttsMessageId) {
      currentAudioRef.current?.pause();
      setActiveTtsMessageId(null);
      return;
    }

    const audioUrl = ttsAudioUrlMapRef.current.get(ttsMessageId);
    if (!audioUrl) {
      warmupTtsAudio(ttsMessageId, true);
      return;
    }

    currentAudioRef.current?.pause();
    const audio = new Audio(audioUrl);
    currentAudioRef.current = audio;

    const idToTrack = ttsMessageId;
    setActiveTtsMessageId(idToTrack);

    const cleanup = () => {
      setActiveTtsMessageId((curr) => curr === idToTrack ? null : curr);
    };
    audio.onended = cleanup;
    audio.onpause = cleanup;
    audio.onerror = cleanup;

    void audio.play()
      .then(() => {
        setActiveTtsMessageId(idToTrack);
      })
      .catch(() => {
        setTtsState(idToTrack, 'error');
        setActiveTtsMessageId((curr) => curr === idToTrack ? null : curr);
      });
  }, [currentLanguage, selectedTtsCharacter, setTtsState, warmupTtsAudio, activeTtsMessageId]);

  const playVoicePreview = useCallback(async () => {
    if (previewingVoice) {
      currentAudioRef.current?.pause();
      currentAudioRef.current = null;
      setPreviewingVoice(false);
      return;
    }

    setPreviewingVoice(true);
    currentAudioRef.current?.pause();
    setActiveTtsMessageId(null);

    try {
      const testText = currentLanguage === 'zh' ? '您好，我是您的語音助手。' : 'Hello, I am your voice assistant.';
      const res = await fetchWithApiKey('/api/hciot/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: testText,
          language: currentLanguage,
          character: selectedTtsCharacter || undefined,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      const id = normalizeTtsMessageId(data?.tts_message_id);
      if (!id) throw new Error('Invalid TTS message ID');

      let audioBlob: Blob | null = null;
      for (let attempt = 0; attempt < 16; attempt += 1) {
        if (isUnmountedRef.current) return;
        const getRes = await fetchWithApiKey(`/api/hciot/tts/${encodeURIComponent(id)}`);
        if (getRes.status === 202) {
          await sleep(Math.min(300 + attempt * 50, 1000));
          continue;
        }
        if (!getRes.ok) throw new Error(await getRes.text());
        audioBlob = await getRes.blob();
        break;
      }

      if (!audioBlob) throw new Error('TTS preview timeout');

      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);
      currentAudioRef.current = audio;

      const cleanup = () => {
        setPreviewingVoice(false);
        URL.revokeObjectURL(audioUrl);
      };
      audio.onended = cleanup;
      audio.onpause = cleanup;
      audio.onerror = cleanup;

      await audio.play();
    } catch (error) {
      console.error('Failed to play voice preview:', error);
      alert('語音播放失敗，請重試');
      setPreviewingVoice(false);
    }
  }, [currentLanguage, selectedTtsCharacter, previewingVoice]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      const now = Date.now();
      messages.forEach((msg) => {
        if (msg.type !== 'assistant') return;
        const id = normalizeTtsMessageId(msg.ttsMessageId);
        if (!id || ttsAudioUrlMapRef.current.has(id)) return;
        const state = ttsStateMap[id];
        if (state === 'pending') {
          const startedAt = ttsPendingSinceRef.current.get(id) || 0;
          if (startedAt > 0 && now - startedAt > TTS_STALL_TIMEOUT_MS) {
            warmupTtsAudio(id, true);
          }
          return;
        }
        if (state === 'ready' || state === 'error') return;
        warmupTtsAudio(id);
      });
    }, TTS_POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [messages, ttsStateMap, warmupTtsAudio]);

  const getAssistantTtsState = useCallback((ttsMessageId?: string): TtsState | undefined => {
    const id = normalizeTtsMessageId(ttsMessageId);
    if (!id) return undefined;
    return ttsStateMap[id];
  }, [ttsStateMap]);

  const switchWorkspace = useCallback((nextWorkspace: WorkspaceMode) => {
    setWorkspace(nextWorkspace);
    writeStoredWorkspace(nextWorkspace);
  }, []);

  useFocusOnOpen(editTextareaRef, editingTurn !== null);

  const resetConversationState = useCallback(() => {
    setLoading(false);
    setIsTyping(false);
    ttsEpochRef.current += 1;
    ttsPendingMapRef.current.clear();
    ttsPendingSinceRef.current.clear();
    currentAudioRef.current?.pause();
    currentAudioRef.current = null;
    setActiveTtsMessageId(null);
    setPreviewingVoice(false);
    ttsAudioUrlMapRef.current.forEach(url => URL.revokeObjectURL(url));
    ttsAudioUrlMapRef.current.clear();
    setTtsStateMap({});
  }, []);

  const startSession = useCallback(async (previousSessionId?: string | null, targetLanguage?: string) => {
    const lang = normalizeHciotLanguage(targetLanguage || currentLanguage);
    const result = await api.hciotStartChat(lang, previousSessionId);
    setSessionId(result.session_id || null);
    setSessionInfo(buildSessionInfo(result.session_id));
    setStatusText(HCIOT_UI_TEXT.statusConnected);
    setStoreMissing(false);
    setMessages(buildOpeningMessages(result.opening_message));
    if (lang !== currentLanguage) {
      setCurrentLanguage(lang);
    }
    focusSoon(inputRef);
    return result.session_id || null;
  }, [currentLanguage]);

  const bootstrapped = useRef(false);

  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;
    startSession()
      .then(() => setStoreName(HCIOT_DEFAULT_STORE_NAME))
      .catch((error) => {
        console.error('Failed to initialize HCIoT session:', error);
        setStoreMissing(true);
        setStatusText(HCIOT_UI_TEXT.statusFailed);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshPublicTopics = useCallback(async () => {
    try {
      const data = await api.listHciotTopics(currentLanguage);
      const nextCategories = data.categories || [];
      if (nextCategories.length) {
        setCategories(nextCategories);
        setTopicSelection((current) => resolveTopicSelection(nextCategories, current));
        setTopicsError(false);
      } else {
        setCategories([]);
        setTopicSelection(EMPTY_TOPIC_SELECTION);
        setTopicsError(true);
      }
    } catch {
      setCategories([]);
      setTopicSelection(EMPTY_TOPIC_SELECTION);
      setTopicsError(true);
    }
  }, [currentLanguage]);

  // Fetch categories from API.
  useEffect(() => {
    void refreshPublicTopics();
  }, [refreshPublicTopics]);

  const restartConversation = useCallback(async () => {
    if (!storeName) return;
    if (messages.some((m) => m.type === 'user') && !window.confirm(HCIOT_UI_TEXT.restartConfirm)) {
      return;
    }
    resetConversationState();
    await startSession(sessionId);
  }, [messages, resetConversationState, sessionId, startSession, storeName]);

  const silentRestartConversation = useCallback(async () => {
    if (!storeName) return;
    resetConversationState();
    await startSession(sessionId);
  }, [resetConversationState, sessionId, startSession, storeName]);

  const toggleLanguage = useCallback(async () => {
    if (messages.some((m) => m.type === 'user')) {
      if (!window.confirm(HCIOT_UI_TEXT.languageConfirm)) {
        return;
      }
    }

    const nextLanguage = currentLanguage === 'zh' ? 'en' : 'zh';
    localStorage.setItem('language', nextLanguage);
    setCurrentLanguage(nextLanguage);

    if (storeName) {
      await startSession(sessionId, nextLanguage);
    }
  }, [currentLanguage, messages, sessionId, startSession, storeName]);

  const sendMessage = useCallback(async (message: string, turnNumber?: number) => {
    if (!message) return;

    setEditingTurn(null);
    if (turnNumber === undefined) {
      setMessages((prev) => [...prev, { text: message, type: 'user', timestamp: Date.now() }]);
    }

    setUserInput('');
    setLoading(true);
    setIsTyping(true);
    focusSoon(inputRef);

    try {
      let activeSessionId = sessionId;
      if (!activeSessionId) {
        activeSessionId = await startSession();
      }
      if (!activeSessionId) throw new Error('Failed to create session');

      const data = await api.hciotSendMessage(
        message,
        activeSessionId,
        turnNumber,
        selectedTtsCharacter,
      );
      await new Promise((resolve) => setTimeout(resolve, 240));
      setIsTyping(false);

      const nextMessage: HciotMessage = {
        text: data.answer,
        type: 'assistant',
        timestamp: Date.now(),
        turnNumber: data.turn_number,
        citations: data.citations,
        imageId: data.image_id,
        ttsText: data.tts_text,
        ttsMessageId: data.tts_message_id,
      };

      if (data.tts_message_id) {
        warmupTtsAudio(data.tts_message_id);
      }

      setMessages((prev) => {
        return [...updateLastUserTurnNumber(prev, data.turn_number), nextMessage];
      });

      setStatusText(HCIOT_UI_TEXT.statusChatting);
    } catch (error) {
      console.error('HCIoT sendMessage failed:', error);
      setIsTyping(false);
      setMessages((prev) => [
        ...prev,
        { text: `⚠️ ${HCIOT_UI_TEXT.networkError}`, type: 'system', timestamp: Date.now() },
      ]);
    } finally {
      setLoading(false);
      focusSoon(inputRef);
    }
  }, [selectedTtsCharacter, sessionId, startSession]);

  const handleRegenerate = async (turnNumber: number) => {
    if (!sessionId || loading) return;
    const userMessageIndex = findUserMessageIndexByTurn(messages, turnNumber);
    const userMessage = userMessageIndex === -1 ? null : messages[userMessageIndex];
    if (!userMessage?.text) return;

    setMessages((prev) => {
      const userIndex = findUserMessageIndexByTurn(prev, turnNumber);
      return userIndex === -1 ? prev : prev.slice(0, userIndex + 1);
    });

    await sendMessage(userMessage.text, turnNumber);
  };

  const handleEditAndResend = async (turnNumber: number, newText: string) => {
    if (!sessionId || loading) return;

    setMessages((prev) => {
      const userIndex = findUserMessageIndexByTurn(prev, turnNumber);
      if (userIndex === -1) return prev;
      return [...prev.slice(0, userIndex), { text: newText, type: 'user', timestamp: Date.now() }];
    });

    await sendMessage(newText, turnNumber);
    setEditingTurn(null);
  };

  const submitEditedMessage = useCallback(() => {
    if (editingTurn !== null && editText.trim()) {
      void handleEditAndResend(editingTurn, editText.trim());
    }
  }, [editText, editingTurn, handleEditAndResend]);

  const submitUserInput = useCallback(() => {
    const trimmed = userInput.trim();
    if (trimmed) {
      void sendMessage(trimmed);
    }
  }, [sendMessage, userInput]);

  const handleEditEnterSubmit = useEnterToSubmit(submitEditedMessage);
  const handleEnterSubmit = useEnterToSubmit(submitUserInput);

  const handleEditKeyDown = (event: React.KeyboardEvent, turnNumber: number) => {
    if (turnNumber === editingTurn) {
      handleEditEnterSubmit(event);
    }
    if (event.key === 'Escape') {
      setEditingTurn(null);
    }
  };

  const handleSubmit = (event: { preventDefault(): void }) => {
    event.preventDefault();
    const trimmed = userInput.trim();
    if (trimmed) {
      void sendMessage(trimmed);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    handleEnterSubmit(event);
  };

  const handleSelectTopic = (topic: HciotTopic) => {
    if (!sessionId || loading) return;
    setSelectedTopicId((prev) => (prev === topic.id ? null : topic.id));
    setIsSidebarOpen(false);
  };

  const handleSelectQuestion = (question: string) => {
    if (!sessionId || loading) return;
    void sendMessage(question);
    setIsSidebarOpen(false);
  };

  const allTopics = useMemo(() => categories.flatMap((cat) => cat.topics), [categories]);
  const selectedCategory = useMemo(
    () => categories.find((cat) => cat.id === selectedCategoryId) || null,
    [categories, selectedCategoryId],
  );
  const visibleTopics = selectedCategory ? selectedCategory.topics : allTopics;
  const topicDisabledMessage = getTopicDisabledMessage(storeMissing, topicsError);

  return (
    <div className="qa-shell">
      <div className="qa-backdrop"></div>

      <header className="qa-header">
        <div className="qa-brand">
          {workspace === 'chat' && (
            <button
              type="button"
              className="qa-sidebar-toggle qa-icon-button"
              onClick={() => setIsSidebarOpen((prev) => !prev)}
              title="科別主題"
              aria-label="科別主題"
              style={{ display: 'none', marginRight: '0.55rem' }}
            >
              <Menu size={20} />
            </button>
          )}
          <div className="qa-brand-mark"><HeartPulse size={24} /></div>
          <div>
            <p className="qa-brand-kicker">{HCIOT_UI_TEXT.brandKicker}</p>
            <h1 className="qa-brand-title">{HCIOT_UI_TEXT.appTitle}</h1>
          </div>
        </div>

        <div className="qa-header-actions">
          <div className="qa-view-toggle" role="tablist" aria-label="工作區切換">
            <button
              type="button"
              className={`qa-view-button${workspace === 'chat' ? ' is-active' : ''}`}
              onClick={() => switchWorkspace('chat')}
            >
              <HeartPulse size={16} />
              <span>聊天</span>
            </button>
            <button
              type="button"
              className={`qa-view-button${workspace === 'files' ? ' is-active' : ''}`}
              onClick={() => switchWorkspace('files')}
            >
              <FileText size={16} />
              <span>檔案管理</span>
            </button>
          </div>
          <div className="qa-tools-menu" ref={toolsMenuRef}>
            <button
              type="button"
              className={`qa-tools-trigger qa-icon-button text${showToolsMenu ? ' is-open' : ''}`}
              onClick={() => setShowToolsMenu((prev) => !prev)}
              title="管理"
              aria-label="管理"
              aria-haspopup="dialog"
              aria-expanded={showToolsMenu}
            >
              <Menu size={16} />
              <span>管理</span>
              <ChevronDown size={14} className="qa-tools-trigger-chevron" />
            </button>
            {showToolsMenu && (
              <div className="qa-tools-popover" role="dialog" aria-label="HCIoT 管理選單">
                <a
                  className="qa-tools-item"
                  href={HCIOT_MANUAL_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={() => setShowToolsMenu(false)}
                >
                  <BookOpen size={16} />
                  <span>{HCIOT_MANUAL_LABEL}</span>
                  <ExternalLink size={13} className="qa-tools-item-external" />
                </a>
                {HCIOT_EXTERNAL_LINK_URL && (
                  <a
                    className="qa-tools-item"
                    href={HCIOT_EXTERNAL_LINK_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={() => setShowToolsMenu(false)}
                  >
                    <Volume2 size={16} />
                    <span>{HCIOT_EXTERNAL_LINK_LABEL}</span>
                    <ExternalLink size={13} className="qa-tools-item-external" />
                  </a>
                )}
                {ttsCharacters.length > 0 && (
                  <div className="qa-tools-voice-panel">
                    <span className="qa-tools-section-label">聲音</span>
                    <div className="qa-tools-voice-row">
                      <HciotSelect
                        className="qa-voice-select"
                        value={selectedTtsCharacter}
                        onChange={setSelectedTtsCharacter}
                        options={ttsCharacters.map((character) => ({ value: character, label: character }))}
                      />
                      <button
                        type="button"
                        className={`qa-voice-preview-btn qa-icon-button${previewingVoice ? ' is-playing' : ''}`}
                        onClick={playVoicePreview}
                        title="試聽選定聲音"
                        aria-label="試聽選定聲音"
                      >
                        {previewingVoice ? <Loader size={14} className="animate-spin" /> : <Volume2 size={14} />}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
          <span className="qa-header-divider" aria-hidden="true" />
          <button className="qa-icon-button" onClick={() => setShowSettingsModal(true)} title={HCIOT_UI_TEXT.settingsTitle}>
            <Settings size={18} />
          </button>
          <button className="qa-icon-button" onClick={() => void restartConversation()} title={HCIOT_UI_TEXT.restartTitle}>
            <RotateCcw size={18} />
          </button>
          <button className="qa-icon-button" onClick={() => setShowHistoryModal(true)} title={HCIOT_UI_TEXT.historyTitle}>
            <History size={18} />
          </button>
          <button className="qa-icon-button text" onClick={() => void toggleLanguage()} title={HCIOT_UI_TEXT.languageTitle}>
            {currentLanguage === 'zh' ? '英文' : '中文'}
          </button>
          <button className="qa-icon-button" onClick={toggleTheme} title={HCIOT_UI_TEXT.themeTitle}>
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          {isSuperAdmin(profile?.role) && (
            <DbSyncButton app="hciot" className="qa-icon-button" />
          )}
          {isAdminRole(profile?.role) && (
            <button
              className="qa-icon-button"
              onClick={() => navigate('/')}
              title="返回後台"
            >
              <ArrowLeft size={18} />
            </button>
          )}
          {profile && (
            <>
              <span className="qa-profile-indicator">
                {profile.username} ({profile.role})
              </span>
              <button
                className="qa-icon-button"
                onClick={() => void handleLogoutClick()}
                title="登出"
              >
                <LogOut size={18} />
              </button>
            </>
          )}
        </div>
      </header>

      <main className="qa-main">
        <section className={`qa-chat-workspace${workspace === 'chat' ? ' is-active' : ''}`}>
          <div
            className={`qa-sidebar-overlay${isSidebarOpen ? ' is-visible' : ''}`}
            onClick={() => setIsSidebarOpen(false)}
          />
          <aside className={`qa-sidebar custom-scrollbar${isSidebarOpen ? ' is-open' : ''}`}>
            <div className="qa-topic-inline-panel">
              <HciotTopicGrid
                topics={visibleTopics}
                categories={categories}
                disabled={loading || !sessionId}
                onSelect={handleSelectTopic}
                onSelectQuestion={handleSelectQuestion}
                selectedTopicId={selectedTopicId}
                selectedCategoryId={selectedCategoryId}
                onSelectCategory={(catId) => {
                  const cat = categories.find((c) => c.id === catId);
                  const firstTopic = cat?.topics[0];
                  setTopicSelection({
                    categoryId: catId,
                    topicId: firstTopic?.id || null,
                  });
                }}
                disabledMessage={topicDisabledMessage}
              />
            </div>
          </aside>

          <div className="qa-chat-container">
            <HciotMessageList
              messages={messages}
              loading={loading}
              isTyping={isTyping}
              editingTurn={editingTurn}
              editText={editText}
              editTextareaRef={editTextareaRef}
              messagesEndRef={messagesEndRef}
              handleRegenerate={handleRegenerate}
              handleEditAndResend={handleEditAndResend}
              setEditingTurn={setEditingTurn}
              setEditText={setEditText}
              handleEditKeyDown={handleEditKeyDown}
              onPlayTts={playAssistantTts}
              getTtsState={getAssistantTtsState}
              activeTtsMessageId={activeTtsMessageId}
            />

            <HciotInputArea
              userInput={userInput}
              sessionId={sessionId}
              statusText={statusText}
              sessionInfo={sessionInfo}
              placeholder={loading ? HCIOT_UI_TEXT.loading : HCIOT_UI_TEXT.inputPlaceholder}
              setUserInput={setUserInput}
              handleSubmit={handleSubmit}
              handleKeyDown={handleKeyDown}
              inputRef={inputRef}
            />
          </div>
        </section>

        <HciotKnowledgeWorkspace
          active={workspace === 'files'}
          language={currentLanguage}
          onTopicsChanged={refreshPublicTopics}
        />
      </main>

      <HciotSettingsModal
        isOpen={showSettingsModal}
        onClose={() => setShowSettingsModal(false)}
        onPromptChange={silentRestartConversation}
        language={currentLanguage}
        sessionId={sessionId}
      />

      <ConversationHistoryModal
        isOpen={showHistoryModal}
        onClose={() => setShowHistoryModal(false)}
        sessionId={sessionId || undefined}
        storeName={storeName || undefined}
        mode="hciot"
        onResumeSession={(sid, resumedMessages) => {
          setSessionId(sid);
          setMessages(
            resumedMessages.map((message, index) => ({
              text: message.text,
              type: message.role === 'assistant' ? 'assistant' : 'user',
              timestamp: Date.now() + index,
              turnNumber: message.turnNumber,
              citations: message.citations,
              imageId: message.imageId,
            })),
          );
          setSessionInfo(buildSessionInfo(sid));
          setStatusText(HCIOT_UI_TEXT.statusConnected);
        }}
      />
    </div>
  );
}
