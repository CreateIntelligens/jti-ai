import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { History, Moon, RotateCcw, Settings, Sun } from 'lucide-react';

import ConversationHistoryModal from '../components/ConversationHistoryModal';
import PromptManagementModal from '../components/PromptManagementModal';
import HciotInputArea from '../components/hciot/HciotInputArea';
import HciotMessageList, { type HciotMessage } from '../components/hciot/HciotMessageList';
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
import type { Store } from '../types';
import '../styles/shared/index.css';
import '../styles/hciot/layout.css';
import '../styles/hciot/components.css';

export default function Hciot() {
  const { t, i18n } = useTranslation();
  const { theme, toggleTheme } = useTheme();

  const [stores, setStores] = useState<Store[]>([]);
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

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const editTextareaRef = useRef<HTMLTextAreaElement>(null);

  useScrollToBottom(messagesEndRef, [messages]);
  useAutoResize(inputRef, userInput);

  useEffect(() => {
    if (editingTurn !== null && editTextareaRef.current) {
      editTextareaRef.current.focus();
      const end = editTextareaRef.current.value.length;
      editTextareaRef.current.setSelectionRange(end, end);
    }
  }, [editingTurn]);

  const startSession = useCallback(async (targetStore: string, previousSessionId?: string | null, targetLanguage?: string) => {
    const lang = normalizeHciotLanguage(targetLanguage || currentLanguage);
    const result = await api.startChat(targetStore, previousSessionId);
    setSessionId(result.session_id || null);
    setSessionInfo(result.session_id ? `#${result.session_id.substring(0, 8)}` : '');
    setStatusText(t('status_connected'));
    setStoreMissing(false);
    if (lang !== currentLanguage) {
      setCurrentLanguage(lang);
    }
    setTimeout(() => inputRef.current?.focus(), 100);
    return result.session_id || null;
  }, [currentLanguage, t]);

  const bootstrapStore = useCallback(async () => {
    try {
      const availableStores = await api.fetchStores();
      setStores(availableStores);

      const targetKey = HCIOT_DEFAULT_STORE_NAME.toLowerCase();
      const target = availableStores.find((store) => {
        const storeName = store.name.toLowerCase();
        const displayName = (store.display_name || '').toLowerCase();
        return storeName === targetKey || displayName === targetKey;
      });
      if (!target) {
        setStoreName(null);
        setStoreMissing(true);
        setSessionId(null);
        setSessionInfo('');
        setStatusText(t('hciot_status_store_missing'));
        return;
      }

      setStoreName(target.name);
      await startSession(target.name);
    } catch (error) {
      console.error('Failed to initialize HCIoT store:', error);
      setStoreMissing(true);
      setStatusText(t('status_failed'));
    }
  }, [startSession, t]);

  useEffect(() => {
    void bootstrapStore();
  }, [bootstrapStore]);

  const restartConversation = useCallback(async () => {
    if (!storeName) return;
    if (messages.length > 0 && !window.confirm(t('restart_confirm'))) {
      return;
    }
    setLoading(false);
    setIsTyping(false);
    setMessages([]);
    await startSession(storeName, sessionId);
  }, [messages.length, sessionId, startSession, storeName, t]);

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
    setMessages([]);

    if (storeName) {
      await startSession(storeName, sessionId, nextLanguage);
    }
  }, [currentLanguage, i18n, messages.length, sessionId, startSession, storeName, t]);

  const sendMessage = useCallback(async (message: string, turnNumber?: number) => {
    if (!message || loading || !storeName) return;

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
        activeSessionId = await startSession(storeName);
      }

      const data = await api.sendMessage(message, activeSessionId || undefined, turnNumber);
      await new Promise((resolve) => setTimeout(resolve, 240));
      setIsTyping(false);

      const nextMessage: HciotMessage = {
        text: data.answer,
        type: 'assistant',
        timestamp: Date.now(),
        turnNumber: data.turn_number,
      };

      setMessages((prev) => {
        const next = [...prev];
        let lastUserMessageIndex = -1;
        for (let index = next.length - 1; index >= 0; index -= 1) {
          if (next[index].type === 'user') {
            lastUserMessageIndex = index;
            break;
          }
        }
        if (lastUserMessageIndex !== -1) {
          next[lastUserMessageIndex].turnNumber = data.turn_number;
        }
        return [...next, nextMessage];
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
  }, [loading, sessionId, startSession, storeName, t]);

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
          <div className="hciot-brand-mark">H</div>
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
        <HciotMessageList
          messages={messages}
          loading={loading}
          sessionId={sessionId}
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
          topics={HCIOT_TOPICS}
          language={currentLanguage}
          onSelectTopic={handleSelectTopic}
          heroEyebrow={t('hciot_hero_eyebrow')}
          heroTitle={t('hciot_hero_title')}
          heroDescription={t('hciot_hero_description')}
          heroNote={t('hciot_hero_note')}
          topicHeading={t('hciot_topic_heading')}
          topicSubheading={t('hciot_topic_subheading')}
          topicDisabledMessage={storeMissing ? t('hciot_store_missing_notice', { store: HCIOT_DEFAULT_STORE_NAME }) : null}
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
      </main>

      <PromptManagementModal
        isOpen={showSettingsModal}
        onClose={() => setShowSettingsModal(false)}
        currentStore={storeName}
        onRestartChat={restartConversation}
        stores={stores}
      />

      <ConversationHistoryModal
        isOpen={showHistoryModal}
        onClose={() => setShowHistoryModal(false)}
        sessionId={sessionId || undefined}
        storeName={storeName || undefined}
        mode="general"
        onResumeSession={(sid, resumedMessages) => {
          setSessionId(sid);
          setMessages(
            resumedMessages.map((message, index) => ({
              text: message.text,
              type: message.role === 'assistant' ? 'assistant' : 'user',
              timestamp: Date.now() + index,
              turnNumber: message.turnNumber,
            })),
          );
          setSessionInfo(`#${sid.substring(0, 8)}`);
          setStatusText(t('status_connected'));
        }}
      />
    </div>
  );
}
