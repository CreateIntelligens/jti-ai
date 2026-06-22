import React, { useState, useRef, useEffect, useCallback } from 'react';
import { BookOpen, MessageSquare, Pencil, Plus, RefreshCw, RotateCcw, Send } from 'lucide-react';
import type { Message } from '../types';
import { useEnterToSubmit } from '../hooks/useEnterToSubmit';
import { useFocusOnOpen } from '../hooks/useFocusOnOpen';
import { useScrollToBottom } from '../hooks/useScrollToBottom';
import CitationsList from './CitationsList';

const QUICK_PROMPTS = ['幫我總結主要內容', '有哪些常見問題？', '請給我快速入門指南'];

interface ChatAreaProps {
  messages: Message[];
  onSendMessage: (text: string) => void;
  disabled: boolean;
  loading: boolean;
  onRegenerate?: (turnNumber: number) => void;
  onEditAndResend?: (turnNumber: number, newText: string) => void;
  /* New props for the redesigned layout */
  currentStoreName?: string | null;
  currentStoreIcon?: string;
  currentProjectName?: string | null;
  currentProjectColor?: string;
  onOpenPromptPanel?: () => void;
  onRestartChat?: () => void;
  onCreateStore?: () => void;
}

export default function ChatArea({
  messages,
  onSendMessage,
  disabled,
  loading,
  onRegenerate,
  onEditAndResend,
  currentStoreName,
  currentStoreIcon,
  currentProjectName,
  currentProjectColor,
  onOpenPromptPanel,
  onRestartChat,
  onCreateStore,
}: ChatAreaProps) {
  const [input, setInput] = useState('');
  const [shouldFocus, setShouldFocus] = useState(false);
  const [editingTurn, setEditingTurn] = useState<number | null>(null);
  const [editText, setEditText] = useState('');
  const chatEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const editTextareaRef = useRef<HTMLTextAreaElement>(null);

  useScrollToBottom(chatEndRef, [messages, loading]);

  useEffect(() => {
    if (shouldFocus && textareaRef.current && !disabled) {
      textareaRef.current.focus();
      setShouldFocus(false);
    }
  }, [shouldFocus, disabled]);

  useFocusOnOpen(editTextareaRef, editingTurn !== null);

  const submitInput = useCallback(() => {
    if (input.trim() && !loading) {
      onSendMessage(input.trim());
      setInput('');
      setShouldFocus(true);
    }
  }, [input, onSendMessage, loading]);

  const handleSubmit = (e: { preventDefault(): void }) => {
    e.preventDefault();
    submitInput();
  };

  const handleKeyDown = useEnterToSubmit(submitInput);

  const handleEditSubmit = useCallback((turnNumber: number) => {
    if (editText.trim() && onEditAndResend) {
      onEditAndResend(turnNumber, editText.trim());
      setEditingTurn(null);
    }
  }, [editText, onEditAndResend]);

  const submitEditedMessage = useCallback(() => {
    if (editingTurn !== null) {
      handleEditSubmit(editingTurn);
    }
  }, [editingTurn, handleEditSubmit]);

  const handleEditEnterSubmit = useEnterToSubmit(submitEditedMessage);

  const handleEditKeyDown = (e: React.KeyboardEvent, turnNumber: number) => {
    if (turnNumber === editingTurn) {
      handleEditEnterSubmit(e);
    }
    if (e.key === 'Escape') setEditingTurn(null);
  };

  const startEditing = (msg: Message) => {
    if (!msg.turnNumber || loading) return;
    setEditingTurn(msg.turnNumber);
    setEditText(msg.text || '');
  };

  const sendQuick = (text: string) => {
    onSendMessage(text);
  };

  const hasStore = Boolean(currentStoreName);

  return (
    <main className="chat-area">
      {/* ── Top bar ── */}
      {hasStore && (
        <div className="chat-topbar">
          <div className="ctl-label">
            <div
              className="ctl-dot"
              style={currentProjectColor ? { background: currentProjectColor } : undefined}
            />
            <span className="ctl-name">{currentStoreName}</span>
            {currentProjectName && (
              <span className="ctl-project">· {currentProjectName}</span>
            )}
          </div>
          <div className="ctl-actions">
            {onRestartChat && (
              <button
                className="icon-btn"
                title="重新開始"
                onClick={onRestartChat}
              >
                <RefreshCw size={18} />
              </button>
            )}
            {onOpenPromptPanel && (
              <button
                className="icon-btn icon-btn-pill"
                title="Prompt 設定"
                onClick={onOpenPromptPanel}
              >
                <MessageSquare size={16} /> Prompt
              </button>
            )}
          </div>
        </div>
      )}

      {/* ── Empty state: no store selected ── */}
      {!hasStore ? (
        <div className="empty-state">
          <div className="empty-icon">
            <BookOpen size={26} />
          </div>
          <div className="empty-title">選擇左側知識庫開始對話</div>
          <div className="empty-sub">
            選擇一個已有的知識庫，或新增新知識庫，系統就會自動建立 RAG 對話 session。
          </div>
          {onCreateStore && (
            <button className="btn btn-primary mt-1" onClick={onCreateStore} >
              <Plus size={14} /> 新增知識庫
            </button>
          )}
        </div>
      ) : messages.length === 0 ? (
        /* ── Empty state: store selected, no messages ── */
        <div className="empty-state">
          <div className="welcome-icon">
            {currentStoreIcon || '📁'}
          </div>
          <div className="empty-title">向「{currentStoreName}」提問</div>
          <div className="empty-sub">
            知識庫已就緒，可以直接提問或點選建議問題：
          </div>
          <div className="welcome-chips">
            {QUICK_PROMPTS.map((p, i) => (
              <button
                key={i}
                className="welcome-chip"
                onClick={() => sendQuick(p)}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      ) : (
        /* ── Messages ── */
        <div className="messages-area">
          {messages.map((msg, idx) => (
            <div key={idx} className={`msg-row ${msg.role}`}>
              {msg.loading ? (
                <div className="msg-bubble model is-loading">
                  <div className="msg-loading">
                    <span />
                    <span />
                    <span />
                  </div>
                </div>
              ) : editingTurn !== null &&
                msg.role === 'user' &&
                msg.turnNumber === editingTurn ? (
                <div className="msg-bubble user">
                  <div className="message-edit-area">
                    <textarea
                      ref={editTextareaRef}
                      className="message-edit-textarea"
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      onKeyDown={(e) => handleEditKeyDown(e, editingTurn)}
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
                </div>
              ) : (
                <>
                  <div
                    className={`msg-bubble ${msg.role}${msg.error ? ' error' : ''}`}
                  >
                    {msg.text}
                  </div>
                  {msg.citations && msg.citations.length > 0 && (
                    <CitationsList citations={msg.citations} messageIndex={idx} />
                  )}
                  <div
                    className="msg-actions"
                    style={{
                      justifyContent:
                        msg.role === 'user' ? 'flex-end' : 'flex-start',
                    }}
                  >
                    {!loading && msg.turnNumber && !msg.error && (
                      <>
                        {msg.role === 'user' && onEditAndResend && (
                          <button
                            className="msg-act-btn"
                            onClick={() => startEditing(msg)}
                            title="編輯並重送"
                          >
                            <Pencil size={12} /> 編輯
                          </button>
                        )}
                        {msg.role === 'model' && onRegenerate && (
                          <button
                            className="msg-act-btn"
                            onClick={() => onRegenerate(msg.turnNumber!)}
                            title="重新生成"
                          >
                            <RotateCcw size={12} /> 重新生成
                          </button>
                        )}
                      </>
                    )}
                  </div>
                </>
              )}
            </div>
          ))}
          <div ref={chatEndRef} />
        </div>
      )}

      {/* ── Input Area ── */}
      <div className="input-area">
        <div className="input-wrap">
          <textarea
            ref={textareaRef}
            className="chat-ta"
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              hasStore
                ? `向「${currentStoreName}」提問...`
                : '請先選擇知識庫...'
            }
            disabled={disabled}
          />
          <button
            className="send-btn"
            onClick={handleSubmit}
            disabled={disabled || !input.trim() || loading}
          >
            <Send />
          </button>
        </div>
        <div className="input-hint">Enter 傳送 · Shift+Enter 換行</div>
      </div>
    </main>
  );
}
