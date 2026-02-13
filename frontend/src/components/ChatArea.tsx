import { useState, useRef, useEffect } from 'react';
import type { Message } from '../types';

interface ChatAreaProps {
  messages: Message[];
  onSendMessage: (text: string) => void;
  disabled: boolean;
  loading: boolean;
  onRegenerate?: (turnNumber: number) => void;
  onEditAndResend?: (turnNumber: number, newText: string) => void;
}

export default function ChatArea({
  messages,
  onSendMessage,
  disabled,
  loading,
  onRegenerate,
  onEditAndResend,
}: ChatAreaProps) {
  const [input, setInput] = useState('');
  const [shouldFocus, setShouldFocus] = useState(false);
  const [editingTurn, setEditingTurn] = useState<number | null>(null);
  const [editText, setEditText] = useState('');
  const chatEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const editTextareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (shouldFocus && textareaRef.current && !disabled) {
      textareaRef.current.focus();
      setShouldFocus(false);
    }
  }, [shouldFocus, disabled]);

  // 進入編輯模式時自動 focus 編輯框
  useEffect(() => {
    if (editingTurn !== null && editTextareaRef.current) {
      editTextareaRef.current.focus();
      // 游標移到最後
      const len = editTextareaRef.current.value.length;
      editTextareaRef.current.setSelectionRange(len, len);
    }
  }, [editingTurn]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim()) {
      onSendMessage(input.trim());
      setInput('');
      setShouldFocus(true);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleEditKeyDown = (e: React.KeyboardEvent, turnNumber: number) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleEditSubmit(turnNumber);
    }
    if (e.key === 'Escape') {
      setEditingTurn(null);
    }
  };

  const handleEditSubmit = (turnNumber: number) => {
    if (editText.trim() && onEditAndResend) {
      onEditAndResend(turnNumber, editText.trim());
      setEditingTurn(null);
    }
  };

  const startEditing = (msg: Message) => {
    if (!msg.turnNumber || loading) return;
    setEditingTurn(msg.turnNumber);
    setEditText(msg.text || '');
  };

  return (
    <main>
      <div className="chat-history" role="log" aria-live="polite" aria-label="對話歷史">
        {messages.length === 0 ? (
          <div className="empty-state">
            <h3>✧ 開始對話 ✧</h3>
            <p>選擇一個知識庫並提出問題</p>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <div
              key={idx}
              className={`message ${msg.role} ${msg.error ? 'error' : ''}`}
              role="article"
              aria-label={msg.role === 'user' ? '使用者訊息' : 'AI 回覆'}
            >
              {msg.loading ? (
                <span className="loading-dots" aria-label="AI 思考中">思考中</span>
              ) : editingTurn !== null && msg.role === 'user' && msg.turnNumber === editingTurn ? (
                /* 編輯模式 */
                <div className="message-edit-area">
                  <textarea
                    ref={editTextareaRef}
                    className="message-edit-textarea"
                    value={editText}
                    onChange={e => setEditText(e.target.value)}
                    onKeyDown={e => handleEditKeyDown(e, editingTurn)}
                    rows={Math.min(editText.split('\n').length + 1, 8)}
                  />
                  <div className="message-edit-actions">
                    <button
                      className="message-edit-btn save"
                      onClick={() => handleEditSubmit(editingTurn)}
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
                  {msg.text}
                  {/* 操作按鈕 - hover 時顯示 */}
                  {!loading && msg.turnNumber && !msg.error && (
                    <div className="message-actions">
                      {msg.role === 'user' && onEditAndResend && (
                        <button
                          className="message-action-btn"
                          onClick={() => startEditing(msg)}
                          title="編輯並重送"
                          aria-label="編輯訊息"
                        >
                          &#9998;
                        </button>
                      )}
                      {msg.role === 'model' && onRegenerate && (
                        <button
                          className="message-action-btn"
                          onClick={() => onRegenerate(msg.turnNumber!)}
                          title="重新生成"
                          aria-label="重新生成回覆"
                        >
                          &#8635;
                        </button>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
          ))
        )}
        <div ref={chatEndRef} />
      </div>

      <form className="input-area" onSubmit={handleSubmit} aria-label="訊息輸入表單">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={disabled ? '請先選擇知識庫...' : '輸入訊息... (Enter 傳送, Shift+Enter 換行)'}
          disabled={disabled}
          aria-label="訊息輸入框"
        />
        <button
          type="submit"
          disabled={disabled || !input.trim()}
          aria-label="傳送訊息"
        >
          ⬡ 傳送
        </button>
      </form>
    </main>
  );
}
