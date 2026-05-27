import React from 'react';

const INPUT_LOADING_PLACEHOLDER = '準備中...';
const INPUT_PLACEHOLDER = '輸入訊息... (Enter 傳送, Shift+Enter 換行)';

interface JtiInputAreaProps {
  userInput: string;
  loading: boolean;
  sessionId: string | null;
  statusText: string;
  sessionInfo: string;
  setUserInput: (value: string) => void;
  handleSubmit: (e: React.FormEvent) => void;
  handleKeyDown: (e: React.KeyboardEvent) => void;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
}

export default function JtiInputArea({
  userInput,
  loading,
  sessionId,
  statusText,
  sessionInfo,
  setUserInput,
  handleSubmit,
  handleKeyDown,
  inputRef,
}: JtiInputAreaProps) {
  return (
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
              placeholder={loading ? INPUT_LOADING_PLACEHOLDER : INPUT_PLACEHOLDER}
              disabled={!sessionId}
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
            disabled={!sessionId || !userInput.trim()}
            aria-label="發送訊息"
          >
            <svg className="send-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
              <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
            </svg>
          </button>
        </div>
      </form>
    </div>
  );
}
