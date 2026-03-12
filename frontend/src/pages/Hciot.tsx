import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { HeartPulse, History, Moon, RotateCcw, Settings, Sun } from 'lucide-react';
import { fetchWithApiKey } from '../services/api';

import ConversationHistoryModal from '../components/ConversationHistoryModal';
import HciotSettingsModal from '../components/HciotSettingsModal';
import HciotInputArea from '../components/hciot/HciotInputArea';
import HciotMessageList, { type HciotMessage } from '../components/hciot/HciotMessageList';
import HciotTopicGrid from '../components/hciot/HciotTopicGrid';
import {
  HCIOT_DEFAULT_STORE_NAME,
  HCIOT_TOPICS,
  normalizeHciotLanguage,
  type HciotTopic,
} from '../config/hciotTopics';
import { useAutoResize } from '../hooks/useAutoResize';
import { useScrollToBottom } from '../hooks/useScrollToBottom';
import { useTheme } from '../hooks/useTheme';
import * as api from '../services/api';
import type { TtsState } from '../types';
import '../styles/shared/index.css';
import '../styles/hciot/layout.css';
import '../styles/hciot/components.css';

const TTS_MAX_ATTEMPTS = 16;
const TTS_POLL_INTERVAL_MS = 3000;
const TTS_STALL_TIMEOUT_MS = 12000;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function normalizeTtsMessageId(ttsMessageId?: string): string {
  return (ttsMessageId || '').trim();
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

export default function Hciot() {
  const { t, i18n } = useTranslation();
  const { theme, toggleTheme } = useTheme();

  const [storeName, setStoreName] = useState<string | null>(null);
  const [storeMissing, setStoreMissing] = useState(false);
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
  const [editingTurn, setEditingTurn] = useState<number | null>(null);
  const [editText, setEditText] = useState('');
  const [ttsStateMap, setTtsStateMap] = useState<Record<string, TtsState>>({});

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
        body: JSON.stringify({ text: sourceText, language: currentLanguage }),
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
  }, [currentLanguage, setTtsState, warmupTtsAudio]);

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

  useEffect(() => {
    if (editingTurn !== null && editTextareaRef.current) {
      editTextareaRef.current.focus();
      const end = editTextareaRef.current.value.length;
      editTextareaRef.current.setSelectionRange(end, end);
    }
  }, [editingTurn]);

  const startSession = useCallback(async (previousSessionId?: string | null, targetLanguage?: string) => {
    const lang = normalizeHciotLanguage(targetLanguage || currentLanguage);
    const result = await api.hciotStartChat(lang, previousSessionId);
    setSessionId(result.session_id || null);
    setSessionInfo(result.session_id ? `#${result.session_id.substring(0, 8)}` : '');
    setStatusText(t('status_connected'));
    setStoreMissing(false);
    const opening = result.opening_message
      ? [{ text: result.opening_message, type: 'assistant' as const, timestamp: Date.now() }]
      : [];
    setMessages(opening);
    if (lang !== currentLanguage) {
      setCurrentLanguage(lang);
    }
    setTimeout(() => inputRef.current?.focus(), 100);
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

  const restartConversation = useCallback(async () => {
    if (!storeName) return;
    if (messages.length > 0 && !window.confirm(t('restart_confirm'))) {
      return;
    }
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
    await startSession(sessionId);
  }, [storeName, messages.length, sessionId, startSession, t]);

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

      const data = await api.hciotSendMessage(message, activeSessionId, turnNumber);
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
        let lastUserIndex = -1;
        for (let index = prev.length - 1; index >= 0; index -= 1) {
          if (prev[index].type === 'user') {
            lastUserIndex = index;
            break;
          }
        }
        return [
          ...prev.map((m, i) =>
            i === lastUserIndex ? { ...m, turnNumber: data.turn_number } : m,
          ),
          nextMessage,
        ];
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
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [loading, sessionId, startSession, t]);

  const handleRegenerate = async (turnNumber: number) => {
    if (!sessionId || loading) return;
    const userMessage = messages.find((message) => message.type === 'user' && message.turnNumber === turnNumber);
    if (!userMessage?.text) return;

    setMessages((prev) => {
      const userIndex = prev.findIndex((message) => message.type === 'user' && message.turnNumber === turnNumber);
      if (userIndex === -1) return prev;
      return prev.slice(0, userIndex + 1);
    });

    await sendMessage(userMessage.text, turnNumber);
  };

  const handleEditAndResend = async (turnNumber: number, newText: string) => {
    if (!sessionId || loading) return;

    setMessages((prev) => {
      const userIndex = prev.findIndex((message) => message.type === 'user' && message.turnNumber === turnNumber);
      if (userIndex === -1) return prev;
      return [...prev.slice(0, userIndex), { text: newText, type: 'user', timestamp: Date.now() }];
    });

    await sendMessage(newText, turnNumber);
    setEditingTurn(null);
  };

  const handleEditKeyDown = (event: React.KeyboardEvent, turnNumber: number) => {
    if (event.nativeEvent.isComposing || event.keyCode === 229) return;
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

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = userInput.trim();
    if (trimmed && !loading) {
      void sendMessage(trimmed);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.nativeEvent.isComposing || event.keyCode === 229) return;
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
    void sendMessage(topic.prompts[currentLanguage]);
  };

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
        <aside className="hciot-sidebar">
          <div className="hciot-topic-inline-panel">
            <HciotTopicGrid
              topics={HCIOT_TOPICS}
              language={currentLanguage}
              disabled={loading || !sessionId}
              onSelect={handleSelectTopic}
              heading={t('hciot_topic_heading')}
              subheading={t('hciot_topic_subheading')}
              disabledMessage={storeMissing ? t('hciot_store_missing_notice', { store: HCIOT_DEFAULT_STORE_NAME }) : null}
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
      </main>

      <HciotSettingsModal
        isOpen={showSettingsModal}
        onClose={() => setShowSettingsModal(false)}
        onPromptChange={restartConversation}
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
          setSessionInfo(`#${sid.substring(0, 8)}`);
          setStatusText(t('status_connected'));
        }}
      />
    </div>
  );
}
