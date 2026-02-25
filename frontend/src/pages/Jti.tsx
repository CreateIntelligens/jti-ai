import { useState, useEffect, useRef, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { History, RotateCcw, Sun, Moon, Settings } from 'lucide-react';
import ConversationHistoryModal from '../components/ConversationHistoryModal';
import JtiSettingsModal from '../components/JtiSettingsModal';
import { fetchWithApiKey } from '../services/api';
import '../styles/Jti.css';
import '../styles/JtiLight.css';

interface Message {
  text: string;
  type: 'user' | 'assistant' | 'system';
  toolCalls?: Array<{ tool: string }>;
  timestamp: number;
  turnNumber?: number;
}

interface SessionData {
  session_id: string;
  step: string;
  answers?: Record<string, string>;
  color_scores?: Record<string, number>;
  color_result_id?: string;
  color_result?: { color_name?: string; title?: string };
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
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    const saved = localStorage.getItem('theme');
    return (saved === 'light' || saved === 'dark') ? saved : 'dark';
  });

  // Apply theme to document
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => prev === 'dark' ? 'light' : 'dark');
  };

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // 編輯相關狀態
  const [editingTurn, setEditingTurn] = useState<number | null>(null);
  const [editText, setEditText] = useState('');
  const editTextareaRef = useRef<HTMLTextAreaElement>(null);

  // 進入編輯模式時自動 focus 編輯框
  useEffect(() => {
    if (editingTurn !== null && editTextareaRef.current) {
      editTextareaRef.current.focus();
      const len = editTextareaRef.current.value.length;
      editTextareaRef.current.setSelectionRange(len, len);
    }
  }, [editingTurn]);

  // 重新開始對話
  const restartConversation = useCallback(async () => {
    if (messages.length > 0) {
      if (!window.confirm(t('restart_confirm'))) {
        return;
      }
    }

    try {
      setLoading(false);
      setIsTyping(false);
      const res = await fetchWithApiKey('/api/jti/chat/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ language: currentLanguage, previous_session_id: sessionId }),
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
  }, [currentLanguage, sessionId, messages.length, t]);

  // 靜默重啟（切換 prompt 後使用，不需確認）
  const silentRestart = useCallback(async () => {
    try {
      setLoading(false);
      setIsTyping(false);
      const res = await fetchWithApiKey('/api/jti/chat/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ language: currentLanguage, previous_session_id: sessionId }),
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
  }, [currentLanguage, sessionId, t]);

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
      setLoading(false);
      setIsTyping(false);
      const res = await fetchWithApiKey('/api/jti/chat/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ language: newLang, previous_session_id: sessionId }),
      });
      const data = await res.json();
      setSessionId(data.session_id);
      setMessages([]);
      setStatusText(t('status_connected'));
      setSessionInfo(`#${data.session_id.substring(0, 8)}`);
    } catch {
      setStatusText(t('status_failed'));
    }
  }, [currentLanguage, sessionId, i18n, messages.length, t]);

  // 初始化 session
  useEffect(() => {
    const lang = localStorage.getItem('language') || 'zh';
    fetchWithApiKey('/api/jti/chat/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ language: lang }),
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

  // 自動調整輸入框高度（直到上限）
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    const styles = window.getComputedStyle(el);
    const maxHeight = parseFloat(styles.maxHeight || '160');
    const nextHeight = Math.min(el.scrollHeight, maxHeight);
    el.style.height = `${nextHeight}px`;
    el.style.overflowY = el.scrollHeight > maxHeight ? 'auto' : 'hidden';
  }, [userInput]);

  const sendMessage = useCallback(async (message: string, turnNumber?: number) => {
    if (!message || !sessionId || loading) return;

    // 清除編輯狀態（新訊息送出前就清掉，避免殘留）
    setEditingTurn(null);

    // 如果不是重新生成 (turnNumber undefined)，則加入 user message
    if (turnNumber === undefined) {
      setMessages(prev => [...prev, { text: message, type: 'user', timestamp: Date.now() }]);
    }

    setUserInput('');
    setLoading(true);
    setIsTyping(true);

    try {
      const payload: any = { session_id: sessionId, message };
      if (turnNumber !== undefined) {
        payload.turn_number = turnNumber;
      }

      const res = await fetchWithApiKey('/api/jti/chat/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      await new Promise(resolve => setTimeout(resolve, 300));
      setIsTyping(false);

      // Console log: 對話記錄
      console.log(`[用戶] ${message}`);
      console.log(`[AI回應] ${data.message} (Turn: ${data.turn_number})`);
      if (data.session) {
        const s = data.session as SessionData;
        const count = Object.keys(s.answers || {}).length;
        if (s.step === 'QUIZ') {
          console.log(`[測驗進度] ${count}/5 題`);
        }
        if (s.color_scores && Object.keys(s.color_scores).length > 0) {
          const sorted = Object.entries(s.color_scores).sort(([, a], [, b]) => (b as number) - (a as number));
          console.log(`[當前分數] ${sorted.map(([k, v]) => `${k}:${v}`).join(' | ')}`);
        }
        if (s.color_result_id) {
          console.log(`[測驗結果] ${s.color_result_id} - ${s.color_result?.title || ''}`);
        }
      }
      if (data.tool_calls?.length) {
        console.log(`[工具呼叫]`, data.tool_calls);
      }

      const newMsg: Message = data.error && !data.message
        ? { text: `⚠️ ${data.error}`, type: 'system', timestamp: Date.now() }
        : {
          text: data.message,
          type: 'assistant',
          toolCalls: data.tool_calls,
          timestamp: Date.now(),
          turnNumber: data.turn_number // 從後端取得 turn_number
        };

      // 如果是重新生成，則更新訊息列表
      if (turnNumber !== undefined) {
        setMessages(prev => {
          // 找到該 turn 的 user message (如果需要)
          // Backend 回傳的 turn_number 是這輪對話的編號 (user answer pair)
          // 我們需要把 user message 也標上 turnNumber

          // 簡單策略：如果是 regenerate，我們已經截斷了後面的訊息 (在 handleRegenerate 中)，
          // 所以現在最後一個 message 應該是 (如果是 edit) 或者 最後的 assistant message 是 loading (如果是 regenerate)

          // 但因為我們在 handleRegenerate 已經 truncate 了，所以這裡直接 append 即可？
          // 其實 handleRegenerate 有 truncate 邏輯。
          // 讓我們看看 handleRegenerate 怎麼寫。
          // 最好這裡是直接 append to end，由 handleRegenerate 負責 truncate。
          // 但需更新剛才那個 user message 的 turnNumber (如果它沒有的話 - 雖然通常這在新對話才有)

          // 為了簡單，我們假設 handleRegenerate 已經處理好了 messages 狀態 (截斷了舊的)
          // 我們只需要 append 新的 assistant message
          // 但是！如果是 EditAndResend，我們剛剛 append 了新的 user message
          // 我們應該把 turnNumber 補上去給那個 user message

          const newMessages = [...prev];
          // 嘗試給最後一個 user message 補上 turnNumber (如果它對應到這次回應)
          // 回應的 turn_number 應該跟最後一個 user message 是同一輪
          let lastUserMsgIndex = -1;
          for (let i = newMessages.length - 1; i >= 0; i--) {
            if (newMessages[i].type === 'user') {
              lastUserMsgIndex = i;
              break;
            }
          }
          if (lastUserMsgIndex !== -1) {
            newMessages[lastUserMsgIndex].turnNumber = data.turn_number;
          }

          return [...newMessages, newMsg];
        });
      } else {
        // 一般發送
        setMessages(prev => {
          const newMessages = [...prev];
          let lastUserMsgIndex = -1;
          for (let i = newMessages.length - 1; i >= 0; i--) {
            if (newMessages[i].type === 'user') {
              lastUserMsgIndex = i;
              break;
            }
          }
          if (lastUserMsgIndex !== -1) {
            newMessages[lastUserMsgIndex].turnNumber = data.turn_number;
          }
          return [...newMessages, newMsg];
        });
      }

      // 更新狀態
      if (data.session) {
        const s = data.session as SessionData;
        const count = Object.keys(s.answers || {}).length;
        const colorName = s.color_result?.color_name || s.color_result_id || '';
        const status = s.step === 'QUIZ' ? `${t('status_quiz')} · ${count}/5`
          : colorName || t('status_chatting');
        setStatusText(status);
      }

      // 清除編輯狀態（防止殘留）
      setEditingTurn(null);
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

  const handleRegenerate = async (turnNumber: number) => {
    if (!sessionId || loading) return;

    // 找到該 turn 的 user message 文字
    const userMsg = messages.find(
      m => m.type === 'user' && m.turnNumber === turnNumber
    );
    if (!userMsg?.text) return;

    // 前端截斷：保留到該 turn 的 user message (包含)，移除之後的所有訊息
    setMessages(prev => {
      const userIdx = prev.findIndex(
        m => m.type === 'user' && m.turnNumber === turnNumber
      );
      if (userIdx === -1) return prev;
      return prev.slice(0, userIdx + 1); // 保留 user message
    });

    // 呼叫 sendMessage，帶上 turnNumber
    // sendMessage 內部 logic 會 handle: 
    // 1. 不會再 add user message to list (因為我們傳了 turnNumber 參數？ 不，sendMessage 的 logic 是 `if (turnNumber === undefined)` 才 add user message)
    // 所以我們呼叫 sendMessage(userMsg.text, turnNumber)
    await sendMessage(userMsg.text, turnNumber);
  };

  const handleEditAndResend = async (turnNumber: number, newText: string) => {
    if (!sessionId || loading) return;

    // 前端截斷：保留到該 turn 之前的所有訊息 (移除該 turn 的 user message 及之後所有)
    setMessages(prev => {
      const userIdx = prev.findIndex(
        m => m.type === 'user' && m.turnNumber === turnNumber
      );
      if (userIdx === -1) return prev;
      const truncated = prev.slice(0, userIdx);
      // 加入新的 user message
      return [...truncated, { text: newText, type: 'user', timestamp: Date.now() }];
    });

    // 呼叫 sendMessage，帶上 turnNumber
    // 這裡我們傳 turnNumber，backend 會 delete logs >= turnNumber
    // 前端 sendMessage 會把 turnNumber 補給剛剛加的 user message
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
    { icon: '🎮', text: t('quick_action_quiz'), msg: t('quick_action_quiz'), primary: true },
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
            <span className="logo-icon">🚬</span>
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
                      {action.icon && <span className="action-icon">{action.icon}</span>}
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
                      {editingTurn !== null && editingTurn === msg.turnNumber && msg.type === 'user' ? (
                        <div className="message-edit-area">
                          <textarea
                            ref={editTextareaRef}
                            className="message-edit-textarea"
                            value={editText}
                            onChange={e => setEditText(e.target.value)}
                            onKeyDown={e => handleEditKeyDown(e, msg.turnNumber!)}
                            rows={Math.min(editText.split('\n').length + 1, 5)}
                          />
                          <div className="message-edit-actions">
                            <button
                              className="message-edit-btn save"
                              onClick={() => msg.turnNumber && handleEditAndResend(msg.turnNumber, editText.trim())}
                              disabled={!editText.trim()}
                            >
                              送出
                            </button>
                            <button
                              className="message-edit-btn cancel"
                              onClick={() => setEditingTurn(null)}
                            >
                              取消
                            </button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <div className="message-text">{msg.text}</div>
                          {msg.toolCalls && msg.toolCalls.length > 0 && (
                            <div className="tool-badge">
                              <span className="tool-icon">⚡</span>
                              <span className="tool-text">
                                {msg.toolCalls.map(t => t.tool).join(' → ')}
                              </span>
                            </div>
                          )}

                          {/* 操作按鈕 - hover 時顯示 */}
                          {!loading && msg.turnNumber && (
                            <div className="message-actions">
                              {msg.type === 'user' && (
                                <button
                                  className="message-action-btn"
                                  onClick={() => {
                                    if (msg.turnNumber && !loading) {
                                      setEditingTurn(msg.turnNumber);
                                      setEditText(msg.text);
                                    }
                                  }}
                                  title="編輯並重送"
                                  aria-label="編輯訊息"
                                >
                                  ✎
                                </button>
                              )}
                              {msg.type === 'assistant' && (
                                <button
                                  className="message-action-btn"
                                  onClick={() => msg.turnNumber && handleRegenerate(msg.turnNumber)}
                                  title="重新生成"
                                  aria-label="重新生成回覆"
                                >
                                  ↻
                                </button>
                              )}
                            </div>
                          )}
                        </>
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
              <div className="input-wrapper">
                <textarea
                  ref={inputRef}
                  className="chat-input"
                  value={userInput}
                  onChange={(e) => setUserInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={loading ? t('status_ready') : t('input_placeholder')}
                  disabled={loading || !sessionId}
                  autoComplete="off"
                  spellCheck={false}
                />
                {/* 狀態列 (輸入框內右下角) */}
                <div className="inline-status">
                  <span className="status-dot"></span>
                  <span className="status-text">{statusText}</span>
                  {sessionInfo && <span className="session-badge">{sessionInfo}</span>}
                </div>
              </div>
              <button
                type="submit"
                className="send-button"
                disabled={loading || !sessionId || !userInput.trim()}
                aria-label="發送訊息"
              >
                {loading ? (
                  <span className="button-spinner"></span>
                ) : (
                  <svg className="send-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
                    <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
                  </svg>
                )}
              </button>
            </div>
          </form>
        </div>
      </main>

      {/* 設定 Modal */}
      <JtiSettingsModal
        isOpen={showSettingsModal}
        onClose={() => setShowSettingsModal(false)}
        onPromptChange={silentRestart}
      />

      {/* 對話歷史 Modal */}
      <ConversationHistoryModal
        isOpen={showHistoryModal}
        onClose={() => setShowHistoryModal(false)}
        sessionId={sessionId || ''}
        mode="jti"
        onResumeSession={async (sid, msgs, lang) => {
          setSessionId(sid);
          setMessages(msgs.map((m) => ({
            text: m.text,
            type: m.role as 'user' | 'assistant',
            timestamp: Date.now(),
            turnNumber: m.turnNumber,
          })));
          setSessionInfo(`#${sid.substring(0, 8)}`);

          // 切換語言（如果有提供且與當前不同）
          if (lang && lang !== currentLanguage) {
            i18n.changeLanguage(lang);
            setCurrentLanguage(lang);
            localStorage.setItem('language', lang);
          }

          // 自動嘗試恢復暫停的測驗
          try {
            const res = await fetchWithApiKey('/api/jti/quiz/resume', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ session_id: sid }),
            });
            if (res.ok) {
              const data = await res.json();
              // 有題目代表測驗已恢復，顯示目前題目
              if (data.session?.step === 'QUIZ' && data.message) {
                setMessages((prev) => [...prev, {
                  text: data.message,
                  type: 'assistant',
                  timestamp: Date.now(),
                }]);
              }
            }
          } catch (err) {
            console.error('[Jti] Auto-resume quiz failed:', err);
          }
        }}
      />
    </div>
  );
}
