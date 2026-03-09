import { useState, useEffect, useRef, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { History, RotateCcw, Sun, Moon, Settings } from 'lucide-react';
import ConversationHistoryModal from '../components/ConversationHistoryModal';
import JtiSettingsModal from '../components/JtiSettingsModal';
import JtiMessageList from '../components/jti/JtiMessageList';
import JtiInputArea from '../components/jti/JtiInputArea';
import { fetchWithApiKey, getJtiRuntimeSettings } from '../services/api';
import { useTheme } from '../hooks/useTheme';
import { useAutoResize } from '../hooks/useAutoResize';
import { useScrollToBottom } from '../hooks/useScrollToBottom';
import '../styles/shared/index.css';
import '../styles/jti/layout.css';
import '../styles/jti/messages.css';
import '../styles/jti/settings.css';
import '../styles/jti/theme-overrides.css';
import '../styles/jti/light.css';

interface Message {
  text: string;
  type: 'user' | 'assistant' | 'system';
  toolCalls?: Array<{ tool: string }>;
  citations?: Array<{ title: string; uri: string; text?: string }>;
  timestamp: number;
  turnNumber?: number;
  ttsText?: string;
  ttsMessageId?: string;
}

interface SessionData {
  session_id: string;
  step: string;
  answers?: Record<string, string>;
  selected_questions?: Array<unknown>;
  color_scores?: Record<string, number>;
  color_result_id?: string;
  color_result?: { color_name?: string; title?: string };
}

interface WelcomeContent {
  title: string;
  description: string;
}

type TtsState = 'pending' | 'ready' | 'error';

function getQuizTotalQuestions(session: SessionData): number {
  return session.selected_questions?.length || 4;
}

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => { window.setTimeout(resolve, ms); });
}

export default function Jti() {
  const { t, i18n } = useTranslation();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [userInput, setUserInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [statusText, setStatusText] = useState(t('status_ready'));
  const [sessionInfo, setSessionInfo] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [currentLanguage, setCurrentLanguage] = useState(i18n.language);
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [welcomeContent, setWelcomeContent] = useState<WelcomeContent | null>(null);
  const [ttsStateMap, setTtsStateMap] = useState<Record<string, TtsState>>({});
  const { theme, toggleTheme } = useTheme();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // 編輯相關狀態
  const [editingTurn, setEditingTurn] = useState<number | null>(null);
  const [editText, setEditText] = useState('');
  const editTextareaRef = useRef<HTMLTextAreaElement>(null);
  const ttsAudioUrlMapRef = useRef<Map<string, string>>(new Map());
  const ttsPendingMapRef = useRef<Map<string, Promise<void>>>(new Map());
  const ttsPendingSinceRef = useRef<Map<string, number>>(new Map());
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const isUnmountedRef = useRef(false);
  const ttsEpochRef = useRef(0);

  const clearTtsState = useCallback(() => {
    ttsEpochRef.current += 1;
    ttsPendingMapRef.current.clear();
    ttsPendingSinceRef.current.clear();
    currentAudioRef.current?.pause();
    currentAudioRef.current = null;
    ttsAudioUrlMapRef.current.forEach(url => URL.revokeObjectURL(url));
    ttsAudioUrlMapRef.current.clear();
    setTtsStateMap({});
  }, []);

  const markTtsError = useCallback((id: string) => {
    ttsPendingSinceRef.current.delete(id);
    setTtsStateMap(prev => ({ ...prev, [id]: 'error' }));
  }, []);

  const isStaleEpoch = useCallback((startEpoch: number) =>
    isUnmountedRef.current || ttsEpochRef.current !== startEpoch
    , []);

  const warmupTtsAudio = useCallback((ttsMessageId?: string, force = false) => {
    const id = (ttsMessageId || '').trim();
    if (!id || ttsAudioUrlMapRef.current.has(id)) return;
    if (ttsPendingMapRef.current.has(id) && !force) return;
    if (force) {
      ttsPendingMapRef.current.delete(id);
    }
    const startEpoch = ttsEpochRef.current;

    const task = (async () => {
      setTtsStateMap(prev => ({ ...prev, [id]: 'pending' }));
      ttsPendingSinceRef.current.set(id, Date.now());
      try {
        const maxAttempts = 16;
        for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
          if (isStaleEpoch(startEpoch)) return;

          const res = await fetchWithApiKey(`/api/jti/tts/${encodeURIComponent(id)}`);

          if (res.status === 202) {
            await sleep(Math.min(350 + attempt * 80, 1200));
            continue;
          }
          if (res.status === 404) {
            markTtsError(id);
            return;
          }
          if (!res.ok) {
            throw new Error(await res.text());
          }

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
          setTtsStateMap(prev => ({ ...prev, [id]: 'ready' }));
          return;
        }
        markTtsError(id);
      } catch {
        if (!isStaleEpoch(startEpoch)) {
          markTtsError(id);
        }
      }
    })().finally(() => {
      ttsPendingMapRef.current.delete(id);
    });

    ttsPendingMapRef.current.set(id, task);
  }, [markTtsError, isStaleEpoch]);

  const playAssistantTts = useCallback(async (msg: Message) => {
    let ttsMessageId = msg.ttsMessageId?.trim() || '';

    if (!ttsMessageId) {
      const sourceText = (msg.ttsText || msg.text || '').trim();
      if (!sourceText) return;

      const createRes = await fetchWithApiKey('/api/jti/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: sourceText, language: currentLanguage }),
      });
      if (!createRes.ok) return;

      const createData = await createRes.json();
      ttsMessageId = String(createData?.tts_message_id || '').trim();
      if (!ttsMessageId) return;

      setMessages(prev => {
        let matched = false;
        return prev.map(item => {
          if (matched) return item;
          if (
            item.timestamp === msg.timestamp &&
            item.type === msg.type &&
            item.turnNumber === msg.turnNumber &&
            item.text === msg.text
          ) {
            matched = true;
            return { ...item, ttsMessageId };
          }
          return item;
        });
      });
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
      setTtsStateMap(prev => ({ ...prev, [ttsMessageId]: 'error' }));
    });
  }, [warmupTtsAudio, currentLanguage]);

  // Auto-recover stalled TTS warmups; skip 'error' state to avoid retrying permanent failures (e.g. 404)
  useEffect(() => {
    const POLL_INTERVAL_MS = 3000;
    const STALL_TIMEOUT_MS = 12000;

    const timer = window.setInterval(() => {
      const now = Date.now();
      messages.forEach(msg => {
        if (msg.type !== 'assistant') return;
        const id = msg.ttsMessageId?.trim();
        if (!id || ttsAudioUrlMapRef.current.has(id)) return;

        const state = ttsStateMap[id];
        if (state === 'pending') {
          const startedAt = ttsPendingSinceRef.current.get(id) || 0;
          if (startedAt > 0 && now - startedAt > STALL_TIMEOUT_MS) {
            warmupTtsAudio(id, true);
          }
          return;
        }

        if (state === 'ready' || state === 'error') return;
        warmupTtsAudio(id);
      });
    }, POLL_INTERVAL_MS);

    return () => window.clearInterval(timer);
  }, [messages, ttsStateMap, warmupTtsAudio]);

  const getAssistantTtsState = useCallback((ttsMessageId?: string): TtsState | undefined => {
    const id = (ttsMessageId || '').trim();
    if (!id) return undefined;
    return ttsStateMap[id];
  }, [ttsStateMap]);

  // 進入編輯模式時自動 focus 編輯框
  useEffect(() => {
    if (editingTurn !== null && editTextareaRef.current) {
      editTextareaRef.current.focus();
      const len = editTextareaRef.current.value.length;
      editTextareaRef.current.setSelectionRange(len, len);
    }
  }, [editingTurn]);

  // Reset unmounted flag on mount (required for HMR/hot reload where ref persists across remounts)
  useEffect(() => {
    isUnmountedRef.current = false;
    return () => {
      isUnmountedRef.current = true;
      clearTtsState();
    };
  }, [clearTtsState]);

  // 建立新 session 的共用邏輯
  const startNewSession = useCallback(async (lang: string) => {
    setLoading(false);
    setIsTyping(false);
    const res = await fetchWithApiKey('/api/jti/chat/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ language: lang, previous_session_id: sessionId }),
    });
    const data = await res.json();
    setSessionId(data.session_id);
    const opening = data.opening_message
      ? [{ text: data.opening_message, type: 'assistant' as const, timestamp: Date.now() }]
      : [];
    setMessages(opening);
    clearTtsState();
    setStatusText(t('status_connected'));
    setSessionInfo(`#${data.session_id.substring(0, 8)}`);
    return data;
  }, [sessionId, t, clearTtsState]);

  const restartConversation = useCallback(async () => {
    if (messages.length > 0 && !window.confirm(t('restart_confirm'))) {
      return;
    }
    try {
      await startNewSession(currentLanguage);
      setTimeout(() => inputRef.current?.focus(), 100);
    } catch {
      setStatusText(t('status_failed'));
    }
  }, [currentLanguage, messages.length, t, startNewSession]);

  const silentRestart = useCallback(async () => {
    try {
      await startNewSession(currentLanguage);
      setTimeout(() => inputRef.current?.focus(), 100);
    } catch {
      setStatusText(t('status_failed'));
    }
  }, [currentLanguage, startNewSession]);

  const toggleLanguage = useCallback(async () => {
    if (messages.length > 0) {
      const confirmMessage = currentLanguage === 'zh'
        ? '切換語言將重新開始對話，確定要繼續嗎？'
        : 'Switching language will restart the conversation. Continue?';
      if (!window.confirm(confirmMessage)) {
        return;
      }
    }

    const newLang = currentLanguage === 'zh' ? 'en' : 'zh';
    i18n.changeLanguage(newLang);
    setCurrentLanguage(newLang);
    localStorage.setItem('language', newLang);

    try {
      await startNewSession(newLang);
    } catch {
      setStatusText(t('status_failed'));
    }
  }, [currentLanguage, i18n, messages.length, t, startNewSession]);

  const refreshWelcomeContent = useCallback(async (lang?: string) => {
    const targetLang = (lang || currentLanguage) === 'en' ? 'en' : 'zh';
    try {
      const data = await getJtiRuntimeSettings(undefined, targetLang);
      const welcome = data.settings?.welcome?.[targetLang];
      if (welcome?.title && welcome?.description) {
        setWelcomeContent({
          title: welcome.title,
          description: welcome.description,
        });
      } else {
        setWelcomeContent(null);
      }
    } catch {
      setWelcomeContent(null);
    }
  }, [currentLanguage]);

  const sessionStarted = useRef(false);

  // 初始化 session（StrictMode 雙呼叫防護，確保只打一次 API）
  useEffect(() => {
    if (sessionStarted.current) return;
    sessionStarted.current = true;
    const lang = localStorage.getItem('language') || 'zh';
    startNewSession(lang)
      .then(() => setTimeout(() => inputRef.current?.focus(), 100))
      .catch(() => setStatusText(t('status_failed')));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void refreshWelcomeContent();
  }, [refreshWelcomeContent]);

  useScrollToBottom(messagesEndRef, [messages]);
  useAutoResize(inputRef, userInput);

  const sendMessage = useCallback(async (message: string, turnNumber?: number) => {
    if (!message || !sessionId || loading) return;

    setEditingTurn(null);

    if (turnNumber === undefined) {
      setMessages(prev => [...prev, { text: message, type: 'user', timestamp: Date.now() }]);
    }

    setUserInput('');
    setLoading(true);
    setIsTyping(true);

    try {
      const postChatMessage = async (activeSessionId: string) => {
        const payload: any = { session_id: activeSessionId, message };
        if (turnNumber !== undefined) {
          payload.turn_number = turnNumber;
        }
        return fetchWithApiKey('/api/jti/chat/message', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      };

      const isSessionNotFoundError = (statusCode: number, bodyText: string) =>
        statusCode === 404 || /session not found/i.test(bodyText);

      let activeSessionId = sessionId;
      let res = await postChatMessage(activeSessionId);

      if (!res.ok) {
        const errorText = await res.text();
        if (isSessionNotFoundError(res.status, errorText)) {
          const restartRes = await fetchWithApiKey('/api/jti/chat/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ language: currentLanguage, previous_session_id: activeSessionId }),
          });
          if (!restartRes.ok) {
            throw new Error(await restartRes.text());
          }
          const restartData = await restartRes.json();
          activeSessionId = restartData.session_id;
          setSessionId(activeSessionId);
          setSessionInfo(`#${activeSessionId.substring(0, 8)}`);
          setStatusText(t('status_connected'));
          clearTtsState();

          res = await postChatMessage(activeSessionId);
          if (!res.ok) {
            const retryErrorText = await res.text();
            throw new Error(retryErrorText || `HTTP ${res.status}`);
          }
        } else {
          throw new Error(errorText || `HTTP ${res.status}`);
        }
      }

      const data = await res.json();
      await new Promise(resolve => setTimeout(resolve, 300));
      setIsTyping(false);

      console.log(`[用戶] ${message}`);
      console.log(`[AI回應] ${data.message} (Turn: ${data.turn_number})`);

      const newMsg: Message = data.error && !data.message
        ? { text: `⚠️ ${data.error}`, type: 'system', timestamp: Date.now() }
        : {
          text: data.message,
          type: 'assistant',
          toolCalls: data.tool_calls,
          citations: data.citations,
          timestamp: Date.now(),
          turnNumber: data.turn_number, // 從後端取得 turn_number
          ttsText: data.tts_text,
          ttsMessageId: data.tts_message_id,
        };

      if (newMsg.type === 'assistant' && newMsg.ttsMessageId) {
        warmupTtsAudio(newMsg.ttsMessageId);
      }

      // 將回應的 turn_number 補到最後一個 user message，並 append assistant 回應
      setMessages(prev => {
        const updated = [...prev];
        let foundUser = false;
        for (let i = updated.length - 1; i >= 0; i--) {
          if (updated[i].type === 'user') {
            updated[i] = { ...updated[i], turnNumber: data.turn_number };
            foundUser = true;
            break;
          }
        }
        if (!foundUser && turnNumber === undefined) {
          updated.push({
            text: message,
            type: 'user',
            timestamp: Date.now(),
            turnNumber: data.turn_number,
          });
        }
        return [...updated, newMsg];
      });

      if (data.session) {
        const s = data.session as SessionData;
        const count = Object.keys(s.answers || {}).length;
        const totalQuestions = getQuizTotalQuestions(s);
        const colorName = s.color_result?.color_name || s.color_result_id || '';
        const status = s.step === 'QUIZ' ? `${t('status_quiz')} · ${count}/${totalQuestions}`
          : colorName || t('status_chatting');
        setStatusText(status);
      }

    } catch (error) {
      setIsTyping(false);
      const errorMessage = error instanceof Error ? error.message : t('error_network');
      setMessages(prev => [...prev, {
        text: `⚠️ ${errorMessage || t('error_network')}`,
        type: 'system',
        timestamp: Date.now()
      }]);
    } finally {
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [sessionId, loading, warmupTtsAudio, currentLanguage, t, clearTtsState]);

  const handleRegenerate = async (turnNumber: number) => {
    if (!sessionId || loading) return;

    const userMsg = messages.find(m => m.type === 'user' && m.turnNumber === turnNumber);
    if (!userMsg?.text) return;

    // 截斷到該 turn 的 user message（含），移除後續訊息
    setMessages(prev => {
      const userIdx = prev.findIndex(m => m.type === 'user' && m.turnNumber === turnNumber);
      if (userIdx === -1) return prev;
      return prev.slice(0, userIdx + 1);
    });

    await sendMessage(userMsg.text, turnNumber);
  };

  const handleEditAndResend = async (turnNumber: number, newText: string) => {
    if (!sessionId || loading) return;

    // 截斷到該 turn 之前，插入新的 user message
    setMessages(prev => {
      const userIdx = prev.findIndex(m => m.type === 'user' && m.turnNumber === turnNumber);
      if (userIdx === -1) return prev;
      return [...prev.slice(0, userIdx), { text: newText, type: 'user' as const, timestamp: Date.now() }];
    });

    await sendMessage(newText, turnNumber);
    setEditingTurn(null);
  };

  const handleEditKeyDown = (e: React.KeyboardEvent, turnNumber: number) => {
    if (e.nativeEvent.isComposing || e.keyCode === 229) return;
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (editText.trim()) {
        handleEditAndResend(turnNumber, editText.trim());
      }
    }
    if (e.key === 'Escape') {
      setEditingTurn(null);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const msg = userInput.trim();
    if (msg && !loading) sendMessage(msg);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.nativeEvent.isComposing || e.keyCode === 229) return;
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      const msg = userInput.trim();
      if (msg && !loading) sendMessage(msg);
    }
  };

  const quickActions = [
    { text: t('quick_action_quiz'), msg: t('quick_action_quiz'), primary: true },
    { text: t('quick_action_htp'), msg: t('quick_action_htp'), primary: false },
    { icon: '👋', text: t('quick_action_greeting'), msg: t('quick_action_greeting'), primary: false },
  ];

  return (
    <div className="jti-container">
      <div className="jti-background">
        <div className="smoke-effect"></div>
        <div className="smoke-effect smoke-2"></div>
      </div>

      <header className="jti-header">
        <div className="header-content">
          <div className="logo-section">
            <h1 className="logo-text">{t('app_title')}</h1>
          </div>
          <div className="status-section">
            <button
              className="icon-btn"
              onClick={() => setShowSettingsModal(true)}
              title={t('settings') || '設定'}
              aria-label="Settings"
            >
              <Settings size={18} />
            </button>
            <button
              className="icon-btn"
              onClick={restartConversation}
              title={t('button_restart')}
              aria-label="Restart Conversation"
            >
              <RotateCcw size={18} />
            </button>
            <button
              className="icon-btn"
              onClick={() => setShowHistoryModal(true)}
              title={t('view_conversation_history') || 'View Conversation History'}
              aria-label="Conversation History"
            >
              <History size={18} />
            </button>
            <button
              className="icon-btn text-icon"
              onClick={toggleLanguage}
              title={currentLanguage === 'zh' ? 'Switch to English' : '切換至繁體中文'}
              aria-label="Toggle Language"
            >
              {currentLanguage === 'zh' ? 'EN' : '中'}
            </button>
            <button
              className="icon-btn"
              onClick={toggleTheme}
              title={theme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
              aria-label="Toggle Theme"
            >
              {theme === 'dark' ? <Moon size={18} /> : <Sun size={18} />}
            </button>
          </div>
        </div>
      </header>

      <main className="jti-main">
        <JtiMessageList
          messages={messages}
          loading={loading}
          sessionId={sessionId}
          isTyping={isTyping}
          editingTurn={editingTurn}
          editText={editText}
          editTextareaRef={editTextareaRef}
          messagesEndRef={messagesEndRef}
          sendMessage={sendMessage}
          handleRegenerate={handleRegenerate}
          handleEditAndResend={handleEditAndResend}
          setEditingTurn={setEditingTurn}
          setEditText={setEditText}
          handleEditKeyDown={handleEditKeyDown}
          quickActions={quickActions}
          welcomeTitle={welcomeContent?.title}
          welcomeDescription={welcomeContent?.description}
          onPlayTts={playAssistantTts}
          getTtsState={getAssistantTtsState}
          t={t}
        />
        {messages.length === 1 && messages[0].type === 'assistant' && (
          <div className="quick-reply-chips">
            {quickActions.map((action, i) => (
              <button
                key={i}
                className={`quick-reply-chip${action.primary ? ' primary' : ''}`}
                onClick={() => sendMessage(action.msg)}
                disabled={loading || !sessionId}
              >
                {action.icon && <span>{action.icon}</span>}
                {action.text}
              </button>
            ))}
          </div>
        )}
        <JtiInputArea
          userInput={userInput}
          loading={loading}
          sessionId={sessionId}
          statusText={statusText}
          sessionInfo={sessionInfo}
          setUserInput={setUserInput}
          handleSubmit={handleSubmit}
          handleKeyDown={handleKeyDown}
          inputRef={inputRef}
          t={t}
        />
      </main>

      {/* 設定 Modal */}
      <JtiSettingsModal
        isOpen={showSettingsModal}
        onClose={() => setShowSettingsModal(false)}
        onPromptChange={() => {
          void silentRestart();
          void refreshWelcomeContent();
        }}
        language={currentLanguage}
      />

      {/* 對話歷史 Modal */}
      <ConversationHistoryModal
        isOpen={showHistoryModal}
        onClose={() => setShowHistoryModal(false)}
        sessionId={sessionId || ''}
        mode="jti"
        onResumeSession={(sid, msgs, lang) => {
          setSessionId(sid);
          setMessages(msgs.map((m) => ({
            text: m.text,
            type: m.role as 'user' | 'assistant',
            timestamp: Date.now(),
            turnNumber: m.turnNumber,
            citations: m.citations,
            ttsText: undefined,
            ttsMessageId: undefined,
          })));
          clearTtsState();
          setSessionInfo(`#${sid.substring(0, 8)}`);

          // 切換語言（如果有提供且與當前不同）
          if (lang && lang !== currentLanguage) {
            i18n.changeLanguage(lang);
            setCurrentLanguage(lang);
            localStorage.setItem('language', lang);
          }

        }}
      />
    </div>
  );
}
