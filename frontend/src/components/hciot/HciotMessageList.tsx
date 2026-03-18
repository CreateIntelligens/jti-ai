import React from 'react';
import type { TtsState } from '../../types';

import CitationsList from '../CitationsList';
import HciotHero from './HciotHero';
import HciotImageAttachment from './HciotImageAttachment';

export interface HciotMessage {
  text: string;
  type: 'user' | 'assistant' | 'system';
  timestamp: number;
  turnNumber?: number;
  citations?: Array<{ title: string; uri: string; text?: string }>;
  imageId?: string;
  ttsText?: string;
  ttsMessageId?: string;
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
  onPlayTts: (msg: HciotMessage) => void;
  getTtsState: (ttsMessageId?: string) => TtsState | undefined;
  heroEyebrow: string;
  heroTitle: string;
  heroDescription: string;
  heroNote: string;
}

function getMessageRoleLabel(type: HciotMessage['type']): string {
  if (type === 'user') return 'You';
  if (type === 'assistant') return 'Guide';
  return 'System';
}

function getAudioButtonTitle(ttsState?: TtsState): string {
  if (ttsState === 'pending') return '語音準備中';
  if (ttsState === 'error') return '語音產生失敗，點擊重試';
  return '播放語音';
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
  onPlayTts,
  getTtsState,
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
          {messages.map((msg, idx) => {
            const isEditingMessage =
              editingTurn !== null && editingTurn === msg.turnNumber && msg.type === 'user';
            const canShowTools = !loading && msg.turnNumber;
            const canPlayTts =
              msg.type === 'assistant' && idx > 0 && Boolean(msg.ttsMessageId || msg.ttsText || msg.text);
            const ttsState = canPlayTts ? getTtsState(msg.ttsMessageId) : undefined;
            const audioButtonClassName = `hciot-audio-btn${ttsState ? ` ${ttsState}` : ''}`;

            return (
              <div
                key={`${msg.timestamp}-${idx}`}
                className={`hciot-message ${msg.type}`}
                style={{ animationDelay: `${idx * 0.04}s` }}
              >
                <div className="hciot-message-meta">
                  <span className="hciot-message-role">{getMessageRoleLabel(msg.type)}</span>
                </div>

                <div className="hciot-message-row">
                  <div className="hciot-message-bubble">
                    {isEditingMessage ? (
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
                        {msg.imageId ? <HciotImageAttachment imageId={msg.imageId} /> : null}
                        {msg.citations && msg.citations.length > 0 ? (
                          <CitationsList citations={msg.citations} messageIndex={idx} />
                        ) : null}
                        {canShowTools ? (
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
                  {canPlayTts ? (
                    <button
                      className={audioButtonClassName}
                      onClick={() => onPlayTts(msg)}
                      title={getAudioButtonTitle(ttsState)}
                      aria-label="播放語音"
                    >
                      <span className="hciot-audio-icon">🔊</span>
                    </button>
                  ) : null}
                </div>
              </div>
            );
          })}

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
