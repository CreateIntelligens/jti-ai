import { useState, useRef, useEffect } from 'react';
import type { Message } from '../types';

interface ChatAreaProps {
  messages: Message[];
  onSendMessage: (text: string) => void;
  disabled: boolean;
  loading: boolean;
}

export default function ChatArea({
  messages,
  onSendMessage,
  disabled,
  loading,
}: ChatAreaProps) {
  const [input, setInput] = useState('');
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim() && !loading) {
      onSendMessage(input.trim());
      setInput('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
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
              role={msg.role === 'user' ? 'article' : 'article'}
              aria-label={msg.role === 'user' ? '使用者訊息' : 'AI 回覆'}
            >
              {msg.loading ? (
                <span className="loading-dots" aria-label="AI 思考中">思考中</span>
              ) : (
                msg.text
              )}
            </div>
          ))
        )}
        <div ref={chatEndRef} />
      </div>

      <form className="input-area" onSubmit={handleSubmit} aria-label="訊息輸入表單">
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={disabled ? '請先選擇知識庫...' : '輸入訊息... (Enter 傳送, Shift+Enter 換行)'}
          disabled={disabled || loading}
          aria-label="訊息輸入框"
        />
        <button
          type="submit"
          disabled={disabled || loading || !input.trim()}
          aria-label="傳送訊息"
        >
          ⬡ 傳送
        </button>
      </form>
    </main>
  );
}
