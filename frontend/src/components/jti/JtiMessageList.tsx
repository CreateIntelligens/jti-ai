import React from 'react';
import type { TFunction } from 'i18next';

function getTtsButtonTitle(ttsState: 'pending' | 'ready' | 'error' | undefined): string {
  if (ttsState === 'pending') return '語音準備中';
  if (ttsState === 'error') return '語音產生失敗，點擊重試';
  return '播放語音';
}

export interface Message {
  text: string;
  type: 'user' | 'assistant' | 'system';
  toolCalls?: Array<{ tool: string }>;
  timestamp: number;
  turnNumber?: number;
  ttsText?: string;
  ttsMessageId?: string;
}

interface QuickAction {
  icon?: string;
  text: string;
  msg: string;
  primary: boolean;
}

interface JtiMessageListProps {
  messages: Message[];
  loading: boolean;
  sessionId: string | null;
  isTyping: boolean;
  editingTurn: number | null;
  editText: string;
  editTextareaRef: React.RefObject<HTMLTextAreaElement | null>;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  sendMessage: (message: string, turnNumber?: number) => void;
  handleRegenerate: (turnNumber: number) => void;
  handleEditAndResend: (turnNumber: number, newText: string) => void;
  onPlayTts: (msg: Message) => void;
  getTtsState: (ttsMessageId?: string) => 'pending' | 'ready' | 'error' | undefined;
  setEditingTurn: (turn: number | null) => void;
  setEditText: (text: string) => void;
  handleEditKeyDown: (e: React.KeyboardEvent, turnNumber: number) => void;
  quickActions: QuickAction[];
  welcomeTitle?: string;
  welcomeDescription?: string;
  t: TFunction;
}

export default function JtiMessageList({
  messages,
  loading,
  sessionId,
  isTyping,
  editingTurn,
  editText,
  editTextareaRef,
  messagesEndRef,
  sendMessage,
  handleRegenerate,
  handleEditAndResend,
  onPlayTts,
  getTtsState,
  setEditingTurn,
  setEditText,
  handleEditKeyDown,
  quickActions,
  welcomeTitle,
  welcomeDescription,
  t,
}: JtiMessageListProps) {
  return (
    <div className="messages-area">
      {messages.length === 0 ? (
        <div className="welcome-screen">
          <div className="welcome-hero">
            <div className="hero-icon-wrapper">
              <span className="hero-icon"></span>
              <div className="icon-glow"></div>
            </div>
            <h2 className="hero-title">{welcomeTitle || t('welcome_title')}</h2>
            <p className="hero-description">
              {welcomeDescription || t('welcome_description')}
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
          {messages.map((msg, idx) => {
            const ttsState = getTtsState(msg.ttsMessageId);
            const audioBtnClass = `message-audio-btn${ttsState ? ` ${ttsState}` : ''}`;

            return (
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
                            <>
                              <button
                                className="message-action-btn"
                                onClick={() => msg.turnNumber && handleRegenerate(msg.turnNumber)}
                                title="重新生成"
                                aria-label="重新生成回覆"
                              >
                                ↻
                              </button>
                            </>
                          )}
                        </div>
                      )}
                    </>
                  )}
                </div>
                  {msg.type === 'assistant' && (msg.ttsMessageId || msg.ttsText || msg.text) && (
                    <button
                      className={audioBtnClass}
                      onClick={() => onPlayTts(msg)}
                      title={getTtsButtonTitle(ttsState)}
                      aria-label="播放語音"
                    >
                      <span className="audio-icon">🔊</span>
                    </button>
                  )}
              </div>
              </div>
            );
          })}

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
  );
}
