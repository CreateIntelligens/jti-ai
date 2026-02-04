import { useState, useEffect, useRef, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import '../styles/JtiTest.css';

interface Message {
  text: string;
  type: 'user' | 'assistant' | 'system';
  toolCalls?: Array<{ tool: string }>;
  timestamp: number;
}

interface SessionData {
  session_id: string;
  step: string;
  answers?: Record<string, string>;
  persona?: string;
}

export default function JtiTest() {
  const { t, i18n } = useTranslation();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [userInput, setUserInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [statusText, setStatusText] = useState(t('status_ready'));
  const [sessionInfo, setSessionInfo] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [currentLanguage, setCurrentLanguage] = useState(i18n.language);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // 重新開始對話
  const restartConversation = useCallback(async () => {
    if (messages.length > 0) {
      if (!window.confirm(t('restart_confirm'))) {
        return;
      }
    }

    try {
      const res = await fetch('/api/mbti/session/new', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'MBTI', language: currentLanguage }),
      });
      const data = await res.json();
      setSessionId(data.session_id);
      setMessages([]);
      setStatusText(t('status_connected'));
      setSessionInfo(`#${data.session_id.substring(0, 8)}`);
      setTimeout(() => inputRef.current?.focus(), 100);
    } catch {
      setStatusText(t('status_failed'));
    }
  }, [currentLanguage, messages.length, t]);

  // 切換語言
  const toggleLanguage = useCallback(async () => {
    // 如果有訊息記錄，警告使用者切換語言會重新開始
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

    // 重新建立 session
    try {
      const res = await fetch('/api/mbti/session/new', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'MBTI', language: newLang }),
      });
      const data = await res.json();
      setSessionId(data.session_id);
      setMessages([]);
      setStatusText(t('status_connected'));
      setSessionInfo(`#${data.session_id.substring(0, 8)}`);
    } catch {
      setStatusText(t('status_failed'));
    }
  }, [currentLanguage, i18n, messages.length, t]);

  // 初始化 session
  useEffect(() => {
    const lang = localStorage.getItem('language') || 'zh';
    fetch('/api/mbti/session/new', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'MBTI', language: lang }),
    })
      .then(res => res.json())
      .then(data => {
        setSessionId(data.session_id);
        setStatusText(t('status_connected'));
        setSessionInfo(`#${data.session_id.substring(0, 8)}`);
        setTimeout(() => inputRef.current?.focus(), 100);
      })
      .catch(() => setStatusText(t('status_failed')));
  }, [t]);

  // 自動滾動到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages]);

  const sendMessage = useCallback(async (message: string) => {
    if (!message || !sessionId || loading) return;

    setMessages(prev => [...prev, { text: message, type: 'user', timestamp: Date.now() }]);
    setUserInput('');
    setLoading(true);
    setIsTyping(true);

    try {
      const res = await fetch('/api/mbti/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message, language: currentLanguage }),
      });

      const data = await res.json();
      await new Promise(resolve => setTimeout(resolve, 300));
      setIsTyping(false);

      const newMsg: Message = data.error && !data.message
        ? { text: `⚠️ ${data.error}`, type: 'system', timestamp: Date.now() }
        : { text: data.message, type: 'assistant', toolCalls: data.tool_calls, timestamp: Date.now() };

      setMessages(prev => [...prev, newMsg]);

      // 更新狀態
      if (data.session) {
        const s = data.session as SessionData;
        const count = Object.keys(s.answers || {}).length;
        const status = s.step === 'QUIZ' ? `${t('status_quiz')} · ${count}/5`
          : s.step === 'RECOMMEND' && s.persona ? `${s.persona}`
          : s.persona || t('status_chatting');
        setStatusText(status);
      }
    } catch {
      setIsTyping(false);
      setMessages(prev => [...prev, {
        text: `⚠️ ${t('error_network')}`,
        type: 'system',
        timestamp: Date.now()
      }]);
    } finally {
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [sessionId, loading]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const msg = userInput.trim();
    if (msg && !loading) sendMessage(msg);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      const msg = userInput.trim();
      if (msg && !loading) sendMessage(msg);
    }
  };

  const quickActions = [
    { icon: '🎮', text: t('quick_action_quiz'), msg: t('quick_action_quiz'), primary: true },
    { icon: '💭', text: t('quick_action_products'), msg: t('quick_action_products'), primary: false },
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
            <span className="logo-icon">🚬</span>
            <h1 className="logo-text">{t('app_title')}</h1>
          </div>
          <div className="status-section">
            <button
              className="restart-button"
              onClick={restartConversation}
              title={t('button_restart')}
            >
              🔄
            </button>
            <button
              className="lang-toggle"
              onClick={toggleLanguage}
              title={currentLanguage === 'zh' ? 'Switch to English' : '切換至繁體中文'}
            >
              {currentLanguage === 'zh' ? 'EN' : '中'}
            </button>
            <div className="status-indicator">
              <span className="status-dot"></span>
              <span className="status-text">{statusText}</span>
            </div>
            {sessionInfo && <span className="session-badge">{sessionInfo}</span>}
          </div>
        </div>
      </header>

      <main className="jti-main">
        <div className="messages-area">
          {messages.length === 0 ? (
            <div className="welcome-screen">
              <div className="welcome-hero">
                <div className="hero-icon-wrapper">
                  <span className="hero-icon">🚬</span>
                  <div className="icon-glow"></div>
                </div>
                <h2 className="hero-title">{t('welcome_title')}</h2>
                <p className="hero-description">
                  {t('welcome_description')}
                </p>
              </div>

              <div className="quick-start">
                <p className="quick-start-label">{t('quick_start')}</p>
                <div className="quick-actions">
                  {quickActions.map((action, i) => (
                    <button
                      key={i}
                      className={`quick-action ${action.primary ? 'primary' : ''}`}
                      onClick={() => sendMessage(action.msg)}
                      disabled={loading || !sessionId}
                    >
                      <span className="action-icon">{action.icon}</span>
                      <span className="action-text">{action.text}</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="messages-container">
              {messages.map((msg, idx) => (
                <div
                  key={`${msg.timestamp}-${idx}`}
                  className={`message ${msg.type}`}
                  style={{ animationDelay: `${idx * 0.05}s` }}
                >
                  <div className="message-wrapper">
                    <div className="message-avatar">
                      <span className="avatar-icon">
                        {msg.type === 'user' ? '👤' : msg.type === 'assistant' ? '🤖' : '💡'}
                      </span>
                    </div>
                    <div className="message-bubble">
                      <div className="message-text">{msg.text}</div>
                      {msg.toolCalls && msg.toolCalls.length > 0 && (
                        <div className="tool-badge">
                          <span className="tool-icon">⚡</span>
                          <span className="tool-text">
                            {msg.toolCalls.map(t => t.tool).join(' → ')}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}

              {isTyping && (
                <div className="message assistant typing-indicator">
                  <div className="message-wrapper">
                    <div className="message-avatar">
                      <span className="avatar-icon">🤖</span>
                    </div>
                    <div className="message-bubble">
                      <div className="typing-dots">
                        <span className="dot"></span>
                        <span className="dot"></span>
                        <span className="dot"></span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        <div className="input-area">
          <form onSubmit={handleSubmit} className="input-form">
            <div className="input-container">
              <input
                ref={inputRef}
                type="text"
                className="chat-input"
                value={userInput}
                onChange={(e) => setUserInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={loading ? t('status_ready') : t('input_placeholder')}
                disabled={loading || !sessionId}
                autoComplete="off"
                spellCheck={false}
              />
              <button
                type="submit"
                className="send-button"
                disabled={loading || !sessionId || !userInput.trim()}
                aria-label="發送訊息"
              >
                {loading ? (
                  <span className="button-spinner"></span>
                ) : (
                  <svg className="send-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
                  </svg>
                )}
              </button>
            </div>
          </form>
        </div>
      </main>
    </div>
  );
}
