interface HciotInputAreaProps {
  userInput: string;
  sessionId: string | null;
  statusText: string;
  sessionInfo: string;
  placeholder: string;
  setUserInput: (value: string) => void;
  handleSubmit: (e: React.FormEvent) => void;
  handleKeyDown: (e: React.KeyboardEvent) => void;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
}

export default function HciotInputArea({
  userInput,
  sessionId,
  statusText,
  sessionInfo,
  placeholder,
  setUserInput,
  handleSubmit,
  handleKeyDown,
  inputRef,
}: HciotInputAreaProps) {
  return (
    <form onSubmit={handleSubmit} className="hciot-input-form">
      <div className="hciot-input-frame">
        <textarea
          ref={inputRef}
          className="hciot-chat-input"
          value={userInput}
          onChange={(e) => setUserInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={!sessionId}
          autoComplete="off"
          spellCheck={false}
        />
        <div className="hciot-input-footer">
          <div className="hciot-inline-status">
            <span className="hciot-status-dot"></span>
            <span>{statusText}</span>
            {sessionInfo ? <span className="hciot-session-chip">{sessionInfo}</span> : null}
          </div>
          <button
            type="submit"
            className="hciot-send-button"
            disabled={!sessionId || !userInput.trim()}
            aria-label="Send message"
          >
            <svg className="hciot-send-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25">
              <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
            </svg>
          </button>
        </div>
      </div>
    </form>
  );
}
