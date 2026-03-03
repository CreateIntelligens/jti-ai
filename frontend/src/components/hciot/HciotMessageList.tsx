import React from 'react';

import HciotHero from './HciotHero';

export interface HciotMessage {
  text: string;
  type: 'user' | 'assistant' | 'system';
  timestamp: number;
  turnNumber?: number;
}

interface HciotMessageListProps {
  messages: HciotMessage[];
  loading: boolean;
  isTyping: boolean;
  editingTurn: number | null;
  editText: string;
  editTextareaRef: React.RefObject<HTMLTextAreaElement | null>;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  handleRegenerate: (turnNumber: number) => void;
  handleEditAndResend: (turnNumber: number, newText: string) => void;
  setEditingTurn: (turn: number | null) => void;
  setEditText: (text: string) => void;
  handleEditKeyDown: (e: React.KeyboardEvent, turnNumber: number) => void;
  heroEyebrow: string;
  heroTitle: string;
  heroDescription: string;
  heroNote: string;
}

export default function HciotMessageList({
  messages,
  loading,
  isTyping,
  editingTurn,
  editText,
  editTextareaRef,
  messagesEndRef,
  handleRegenerate,
  handleEditAndResend,
  setEditingTurn,
  setEditText,
  handleEditKeyDown,
  heroEyebrow,
  heroTitle,
  heroDescription,
  heroNote,
}: HciotMessageListProps) {
  return (
    <div className="hciot-messages-area">
      {messages.length === 0 ? (
        <div className="hciot-empty-state">
          <HciotHero
            eyebrow={heroEyebrow}
            title={heroTitle}
            description={heroDescription}
            note={heroNote}
          />
        </div>
      ) : (
        <div className="hciot-message-thread">
          {messages.map((msg, idx) => (
            <div
              key={`${msg.timestamp}-${idx}`}
              className={`hciot-message ${msg.type}`}
              style={{ animationDelay: `${idx * 0.04}s` }}
            >
              <div className="hciot-message-meta">
                <span className="hciot-message-role">
                  {msg.type === 'user' ? 'You' : msg.type === 'assistant' ? 'Guide' : 'System'}
                </span>
              </div>

              <div className="hciot-message-bubble">
                {editingTurn !== null && editingTurn === msg.turnNumber && msg.type === 'user' ? (
                  <div className="hciot-message-edit">
                    <textarea
                      ref={editTextareaRef}
                      className="hciot-message-edit-textarea"
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      onKeyDown={(e) => handleEditKeyDown(e, msg.turnNumber!)}
                      rows={Math.min(editText.split('\n').length + 1, 6)}
                    />
                    <div className="hciot-message-actions-row">
                      <button
                        type="button"
                        className="hciot-message-action primary"
                        onClick={() => msg.turnNumber && handleEditAndResend(msg.turnNumber, editText.trim())}
                        disabled={!editText.trim()}
                      >
                        Send
                      </button>
                      <button
                        type="button"
                        className="hciot-message-action"
                        onClick={() => setEditingTurn(null)}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="hciot-message-text">{msg.text}</div>
                    {!loading && msg.turnNumber ? (
                      <div className="hciot-message-tools">
                        {msg.type === 'user' ? (
                          <button
                            type="button"
                            className="hciot-inline-action"
                            onClick={() => {
                              setEditingTurn(msg.turnNumber!);
                              setEditText(msg.text);
                            }}
                          >
                            Edit
                          </button>
                        ) : null}
                        {msg.type === 'assistant' ? (
                          <button
                            type="button"
                            className="hciot-inline-action"
                            onClick={() => handleRegenerate(msg.turnNumber!)}
                          >
                            Retry
                          </button>
                        ) : null}
                      </div>
                    ) : null}
                  </>
                )}
              </div>
            </div>
          ))}

          {isTyping ? (
            <div className="hciot-message assistant typing">
              <div className="hciot-message-meta">
                <span className="hciot-message-role">Guide</span>
              </div>
              <div className="hciot-message-bubble">
                <div className="hciot-typing-dots">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
            </div>
          ) : null}

          <div ref={messagesEndRef} />
        </div>
      )}
    </div>
  );
}
