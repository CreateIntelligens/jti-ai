import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';
import { FileText, HeartPulse, History, Moon, RotateCcw, Settings, Sun } from 'lucide-react';
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
import { useScrollToBottom } from '../hooks/useScrollToBottom';
import { useTheme } from '../hooks/useTheme';
import * as api from '../services/api';
import type { TtsState } from '../types';
import '../styles/shared/index.css';
import '../styles/shared/settings.css';
import '../styles/hciot/layout.css';
import '../styles/hciot/components.css';
import '../styles/hciot/components-chat.css';
import '../styles/hciot/components-topic.css';
import '../styles/hciot/workspace.css';
import '../styles/hciot/workspace-upload.css';
import '../styles/hciot/workspace-table.css';
import '../styles/hciot/workspace-images.css';

const TTS_MAX_ATTEMPTS = 16;
const TTS_POLL_INTERVAL_MS = 3000;
const TTS_STALL_TIMEOUT_MS = 12000;
const TTS_CHARACTER_STORAGE_KEY = 'hciot:tts-character';
const WORKSPACE_STORAGE_KEY = 'hciot:workspace';
type WorkspaceMode = 'chat' | 'files';

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
  const { t, i18n } = useTranslation();
  const { theme, toggleTheme } = useTheme();

  const [storeName, setStoreName] = useState<string | null>(null);
  const [storeMissing, setStoreMissing] = useState(false);
  const [topicsError, setTopicsError] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<HciotMessage[]>([]);
  const [userInput, setUserInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [statusText, setStatusText] = useState(t('status_ready'));
  const [sessionInfo, setSessionInfo] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [currentLanguage, setCurrentLanguage] = useState(normalizeHciotLanguage(i18n.language));
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [workspace, setWorkspace] = useState<WorkspaceMode>(() => readStoredWorkspace());
  const [editingTurn, setEditingTurn] = useState<number | null>(null);
  const [editText, setEditText] = useState('');
  const [selectedTopicId, setSelectedTopicId] = useState<string | null>(null);
  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>(null);
  const [categories, setCategories] = useState<HciotCategory[]>([]);
  const [ttsStateMap, setTtsStateMap] = useState<Record<string, TtsState>>({});
  const [ttsCharacters, setTtsCharacters] = useState<string[]>([]);
  const [selectedTtsCharacter, setSelectedTtsCharacter] = useState<string>(
    () => readStoredTtsCharacter(),
  );

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const editTextareaRef = useRef<HTMLTextAreaElement>(null);
  const ttsAudioUrlMapRef = useRef<Map<string, string>>(new Map());
  const ttsPendingMapRef = useRef<Map<string, Promise<void>>>(new Map());
  const ttsPendingSinceRef = useRef<Map<string, number>>(new Map());
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const isUnmountedRef = useRef(false);
  const ttsEpochRef = useRef(0);

  useScrollToBottom(messagesEndRef, [messages]);
  useAutoResize(inputRef, userInput);

  useEffect(() => {
    isUnmountedRef.current = false;
    return () => { isUnmountedRef.current = true; };
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
    const audioUrl = ttsAudioUrlMapRef.current.get(ttsMessageId);
    if (!audioUrl) {
      warmupTtsAudio(ttsMessageId, true);
      return;
    }
    currentAudioRef.current?.pause();
    const audio = new Audio(audioUrl);
    currentAudioRef.current = audio;
    void audio.play().catch(() => {
      setTtsState(ttsMessageId, 'error');
    });
  }, [currentLanguage, selectedTtsCharacter, setTtsState, warmupTtsAudio]);

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

  useEffect(() => {
    if (editingTurn !== null && editTextareaRef.current) {
      editTextareaRef.current.focus();
      const end = editTextareaRef.current.value.length;
      editTextareaRef.current.setSelectionRange(end, end);
    }
  }, [editingTurn]);

  const resetConversationState = useCallback(() => {
    setLoading(false);
    setIsTyping(false);
    ttsEpochRef.current += 1;
    ttsPendingMapRef.current.clear();
    ttsPendingSinceRef.current.clear();
    currentAudioRef.current?.pause();
    currentAudioRef.current = null;
    ttsAudioUrlMapRef.current.forEach(url => URL.revokeObjectURL(url));
    ttsAudioUrlMapRef.current.clear();
    setTtsStateMap({});
  }, []);

  const startSession = useCallback(async (previousSessionId?: string | null, targetLanguage?: string) => {
    const lang = normalizeHciotLanguage(targetLanguage || currentLanguage);
    const result = await api.hciotStartChat(lang, previousSessionId);
    setSessionId(result.session_id || null);
    setSessionInfo(buildSessionInfo(result.session_id));
    setStatusText(t('status_connected'));
    setStoreMissing(false);
    setMessages(buildOpeningMessages(result.opening_message));
    if (lang !== currentLanguage) {
      setCurrentLanguage(lang);
    }
    focusSoon(inputRef);
    return result.session_id || null;
  }, [currentLanguage, t]);

  const bootstrapped = useRef(false);

  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;
    startSession()
      .then(() => setStoreName(HCIOT_DEFAULT_STORE_NAME))
      .catch((error) => {
        console.error('Failed to initialize HCIoT session:', error);
        setStoreMissing(true);
        setStatusText(t('status_failed'));
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Fetch categories from API.
  useEffect(() => {
    fetchWithApiKey('/api/hciot/topics')
      .then((res) => res.ok ? res.json() : Promise.reject(res.status))
      .then((data: { categories: HciotCategory[] }) => {
        if (data.categories?.length) {
          setCategories(data.categories);
          setSelectedCategoryId(data.categories[0].id);
          const firstTopic = data.categories[0].topics[0];
          if (firstTopic) setSelectedTopicId(firstTopic.id);
          setTopicsError(false);
        } else {
          setTopicsError(true);
        }
      })
      .catch(() => {
        setTopicsError(true);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const restartConversation = useCallback(async () => {
    if (!storeName) return;
    if (messages.length > 0 && !window.confirm(t('restart_confirm'))) {
      return;
    }
    resetConversationState();
    await startSession(sessionId);
  }, [messages.length, resetConversationState, sessionId, startSession, storeName, t]);

  const silentRestartConversation = useCallback(async () => {
    if (!storeName) return;
    resetConversationState();
    await startSession(sessionId);
  }, [resetConversationState, sessionId, startSession, storeName]);

  const toggleLanguage = useCallback(async () => {
    if (messages.length > 0) {
      const confirmMessage = currentLanguage === 'zh'
        ? t('hciot_language_confirm_zh')
        : t('hciot_language_confirm_en');
      if (!window.confirm(confirmMessage)) {
        return;
      }
    }

    const nextLanguage = currentLanguage === 'zh' ? 'en' : 'zh';
    i18n.changeLanguage(nextLanguage);
    localStorage.setItem('language', nextLanguage);
    setCurrentLanguage(nextLanguage);

    if (storeName) {
      await startSession(sessionId, nextLanguage);
    }
  }, [currentLanguage, i18n, messages.length, sessionId, startSession, storeName, t]);

  const sendMessage = useCallback(async (message: string, turnNumber?: number) => {
    if (!message || loading) return;

    setEditingTurn(null);
    if (turnNumber === undefined) {
      setMessages((prev) => [...prev, { text: message, type: 'user', timestamp: Date.now() }]);
    }

    setUserInput('');
    setLoading(true);
    setIsTyping(true);

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

      setStatusText(t('status_chatting'));
    } catch (error) {
      console.error('HCIoT sendMessage failed:', error);
      setIsTyping(false);
      setMessages((prev) => [
        ...prev,
        { text: `⚠️ ${t('error_network')}`, type: 'system', timestamp: Date.now() },
      ]);
    } finally {
      setLoading(false);
      focusSoon(inputRef);
    }
  }, [loading, selectedTtsCharacter, sessionId, startSession, t]);

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

  const handleEditKeyDown = (event: React.KeyboardEvent, turnNumber: number) => {
    if (event.nativeEvent.isComposing) return;
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      if (editText.trim()) {
        void handleEditAndResend(turnNumber, editText.trim());
      }
    }
    if (event.key === 'Escape') {
      setEditingTurn(null);
    }
  };

  const handleSubmit = (event: { preventDefault(): void }) => {
    event.preventDefault();
    const trimmed = userInput.trim();
    if (trimmed && !loading) {
      void sendMessage(trimmed);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.nativeEvent.isComposing) return;
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      const trimmed = userInput.trim();
      if (trimmed && !loading) {
        void sendMessage(trimmed);
      }
    }
  };

  const handleSelectTopic = (topic: HciotTopic) => {
    if (!sessionId || loading) return;
    setSelectedTopicId((prev) => (prev === topic.id ? null : topic.id));
  };

  const handleSelectQuestion = (question: string) => {
    if (!sessionId || loading) return;
    void sendMessage(question);
  };

  const allTopics = useMemo(() => categories.flatMap((cat) => cat.topics), [categories]);
  const selectedTopic = useMemo(
    () => allTopics.find((topic) => topic.id === selectedTopicId) || null,
    [allTopics, selectedTopicId],
  );
  const selectedCategory = useMemo(
    () => categories.find((cat) => cat.id === selectedCategoryId) || null,
    [categories, selectedCategoryId],
  );
  const visibleTopics = selectedCategory ? selectedCategory.topics : allTopics;

  return (
    <div className="hciot-shell">
      <div className="hciot-backdrop"></div>

      <header className="hciot-header">
        <div className="hciot-brand">
          <div className="hciot-brand-mark"><HeartPulse size={24} /></div>
          <div>
            <p className="hciot-brand-kicker">{t('hciot_brand_kicker')}</p>
            <h1 className="hciot-brand-title">{t('hciot_app_title')}</h1>
          </div>
        </div>

        <div className="hciot-header-actions">
          <div className="hciot-view-toggle" role="tablist" aria-label={currentLanguage === 'zh' ? '工作區切換' : 'Workspace switcher'}>
            <button
              type="button"
              className={`hciot-view-button${workspace === 'chat' ? ' is-active' : ''}`}
              onClick={() => switchWorkspace('chat')}
            >
              <HeartPulse size={16} />
              <span>{currentLanguage === 'zh' ? '聊天' : 'Chat'}</span>
            </button>
            <button
              type="button"
              className={`hciot-view-button${workspace === 'files' ? ' is-active' : ''}`}
              onClick={() => switchWorkspace('files')}
            >
              <FileText size={16} />
              <span>{currentLanguage === 'zh' ? '檔案管理' : 'Files'}</span>
            </button>
          </div>
          {ttsCharacters.length > 0 && (
            <label className="hciot-voice-select-wrap">
              <span className="hciot-voice-select-label">
                {currentLanguage === 'zh' ? '聲音' : 'Voice'}
              </span>
              <HciotSelect
                className="hciot-voice-select"
                value={selectedTtsCharacter}
                onChange={setSelectedTtsCharacter}
                options={ttsCharacters.map((character) => ({ value: character, label: character }))}
              />
            </label>
          )}
          <button className="hciot-icon-button" onClick={() => setShowSettingsModal(true)} title={t('hciot_settings')}>
            <Settings size={18} />
          </button>
          <button className="hciot-icon-button" onClick={() => void restartConversation()} title={t('button_restart')}>
            <RotateCcw size={18} />
          </button>
          <button className="hciot-icon-button" onClick={() => setShowHistoryModal(true)} title={t('view_conversation_history')}>
            <History size={18} />
          </button>
          <button className="hciot-icon-button text" onClick={() => void toggleLanguage()} title={t('hciot_toggle_language')}>
            {currentLanguage === 'zh' ? 'EN' : '中'}
          </button>
          <button className="hciot-icon-button" onClick={toggleTheme} title={t('hciot_toggle_theme')}>
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </div>
      </header>

      <main className="hciot-main">
        <section className={`hciot-chat-workspace${workspace === 'chat' ? ' is-active' : ''}`}>
          <aside className="hciot-sidebar custom-scrollbar">
            <div className="hciot-topic-inline-panel">
              <HciotTopicGrid
                topics={visibleTopics}
                categories={categories}
                language={currentLanguage}
                disabled={loading || !sessionId}
                onSelect={handleSelectTopic}
                onSelectQuestion={handleSelectQuestion}
                selectedTopicId={selectedTopicId}
                selectedCategoryId={selectedCategoryId}
                onSelectCategory={(catId) => {
                  setSelectedCategoryId(catId);
                  const cat = categories.find((c) => c.id === catId);
                  const firstTopic = cat?.topics[0];
                  setSelectedTopicId(firstTopic?.id || null);
                }}
                heading={t('hciot_topic_heading')}
                subheading={t('hciot_topic_subheading')}
                questionHeading={
                  selectedTopic
                    ? `${selectedTopic.labels[currentLanguage]} ${currentLanguage === 'zh' ? '常見問題' : 'Questions'}`
                    : undefined
                }
                disabledMessage={
                  storeMissing
                    ? t('hciot_store_missing_notice', { store: HCIOT_DEFAULT_STORE_NAME })
                    : topicsError
                      ? (currentLanguage === 'zh' ? '無法載入題目分類，請稍後再試。' : 'Failed to load topics. Please try again later.')
                      : null
                }
              />
            </div>
          </aside>

          <div className="hciot-chat-container">
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
              heroEyebrow={t('hciot_hero_eyebrow')}
              heroTitle={t('hciot_hero_title')}
              heroDescription={t('hciot_hero_description')}
              heroNote={t('hciot_hero_note')}
            />

            <HciotInputArea
              userInput={userInput}
              loading={loading}
              sessionId={sessionId}
              statusText={statusText}
              sessionInfo={sessionInfo}
              placeholder={loading ? t('loading') : t('hciot_input_placeholder')}
              setUserInput={setUserInput}
              handleSubmit={handleSubmit}
              handleKeyDown={handleKeyDown}
              inputRef={inputRef}
            />
          </div>
        </section>

        <HciotKnowledgeWorkspace
          active={workspace === 'files'}
          language="zh"
        />
      </main>

      <HciotSettingsModal
        isOpen={showSettingsModal}
        onClose={() => setShowSettingsModal(false)}
        onPromptChange={silentRestartConversation}
        language={currentLanguage}
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
          setStatusText(t('status_connected'));
        }}
      />
    </div>
  );
}
