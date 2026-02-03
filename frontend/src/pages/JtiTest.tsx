import { useState, useEffect, useRef, useCallback } from 'react';
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
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [userInput, setUserInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [statusText, setStatusText] = useState('正在連接...');
  const [sessionInfo, setSessionInfo] = useState('');
  const [isTyping, setIsTyping] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // 初始化 session
  useEffect(() => {
    fetch('/api/mbti/session/new', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'MBTI' }),
    })
      .then(res => res.json())
      .then(data => {
        setSessionId(data.session_id);
        setStatusText('已連線');
        setSessionInfo(`#${data.session_id.substring(0, 8)}`);
        setTimeout(() => inputRef.current?.focus(), 100);
      })
      .catch(() => setStatusText('連線失敗'));
  }, []);

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
        body: JSON.stringify({ session_id: sessionId, message }),
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
        const status = s.step === 'QUIZ' ? `測驗進行中 · ${count}/5`
          : s.step === 'RECOMMEND' && s.persona ? `性格類型 · ${s.persona}`
          : s.persona || '對話中';
        setStatusText(status);
      }
    } catch {
      setIsTyping(false);
      setMessages(prev => [...prev, {
        text: '⚠️ 網路連線異常，請稍後再試',
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
    { icon: '🎮', text: '開始 MBTI 測驗', msg: '我想做 MBTI 測驗', primary: true },
    { icon: '💭', text: '了解產品', msg: '加熱菸是什麼？', primary: false },
    { icon: '👋', text: '打個招呼', msg: '你好', primary: false },
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
            <h1 className="logo-text">JTI 智慧助手</h1>
          </div>
          <div className="status-section">
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
                <h2 className="hero-title">歡迎使用 JTI 智慧助手</h2>
                <p className="hero-description">
                  透過 AI 驅動的對話系統，幫助您了解自己的性格特質，
                  <br />
                  並為您推薦最適合的 JTI 產品。
                </p>
              </div>

              <div className="quick-start">
                <p className="quick-start-label">快速開始</p>
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
                placeholder={loading ? '處理中...' : '輸入訊息...'}
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
