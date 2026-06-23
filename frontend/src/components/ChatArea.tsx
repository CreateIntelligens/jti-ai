import React, { useState, useRef, useEffect, useCallback, useLayoutEffect, type ReactNode } from 'react';
import { BookOpen, FileText, ListChecks, MessageSquare, Pencil, Plus, RotateCcw, Send } from 'lucide-react';
import type { Message } from '../types';
import { useEnterToSubmit } from '../hooks/useEnterToSubmit';
import { useFocusOnOpen } from '../hooks/useFocusOnOpen';
import { useScrollToBottom } from '../hooks/useScrollToBottom';
import CitationsList from './CitationsList';

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
  /* Prompt 設定改由 Header 設定選單開啟；重新開始功能依設計稿移除。
     仍保留這兩個選用 prop 以相容上層呼叫端，但 topbar 不再渲染。 */
  onOpenPromptPanel?: () => void;
  onRestartChat?: () => void;
  onCreateStore?: () => void;
  onOpenTopics?: () => void;
  topicsOpen?: boolean;
  topicsDisabled?: boolean;
  quickPrompts?: string[];
  quickPromptsLoading?: boolean;
  quickPromptsMessage?: string;
  /* 對話 / 文件 檢視切換（topbar segmented toggle）。
     viewMode==='files' 時下方內容區改 render filesView，並隱藏輸入框。 */
  viewMode?: 'chat' | 'files';
  onChangeView?: (mode: 'chat' | 'files') => void;
  filesViewEnabled?: boolean;
  filesView?: ReactNode;
  /* chat 右側常駐「常見問題」側欄（suggestOpen 時顯示）。 */
  suggestSidebar?: ReactNode;
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
  onCreateStore,
  onOpenTopics,
  topicsOpen = false,
  topicsDisabled = false,
  quickPrompts = [],
  quickPromptsLoading = false,
  quickPromptsMessage,
  viewMode = 'chat',
  onChangeView,
  filesViewEnabled = false,
  filesView,
  suggestSidebar,
}: ChatAreaProps) {
  const [input, setInput] = useState('');
  const [shouldFocus, setShouldFocus] = useState(false);
  const [editingTurn, setEditingTurn] = useState<number | null>(null);
  const [editText, setEditText] = useState('');
  const chatEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const editTextareaRef = useRef<HTMLTextAreaElement>(null);

  useScrollToBottom(chatEndRef, [messages, loading]);

  const resizeComposer = useCallback((element: HTMLTextAreaElement | null) => {
    if (!element) return;
    element.style.height = 'auto';
    if (element.scrollHeight <= 0) return;
    const rootFontSize = Number.parseFloat(
      window.getComputedStyle(document.documentElement).fontSize,
    ) || 16;
    element.style.height = `${Math.min(element.scrollHeight / rootFontSize, 8)}rem`;
  }, []);

  useLayoutEffect(() => {
    resizeComposer(textareaRef.current);
  }, [input, resizeComposer]);

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
    <main className={`chat-area${viewMode === 'files' ? ' is-files-view' : ''}`}>
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
            {viewMode === 'chat' && onOpenTopics && (
              <button
                className={`icon-btn icon-btn-pill general-topics-btn${topicsOpen ? ' active' : ''}`}
                title="常見問題"
                onClick={onOpenTopics}
                disabled={topicsDisabled}
                aria-expanded={topicsOpen}
                aria-controls="general-suggest-sidebar"
              >
                <ListChecks size={16} /> 常見問題
              </button>
            )}
            {filesViewEnabled && onChangeView && (
              <div className="view-toggle" role="tablist" aria-label="檢視切換">
                <button
                  type="button"
                  role="tab"
                  aria-selected={viewMode === 'chat'}
                  className={`view-tab${viewMode === 'chat' ? ' active' : ''}`}
                  onClick={() => onChangeView('chat')}
                >
                  <MessageSquare size={14} /> 對話
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={viewMode === 'files'}
                  className={`view-tab${viewMode === 'files' ? ' active' : ''}`}
                  onClick={() => onChangeView('files')}
                >
                  <FileText size={14} /> 文件
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Files view (knowledge workspace) ── */}
      {viewMode === 'files' && filesView ? (
        <div className="chat-files-view">{filesView}</div>
      ) : (
        <div className="chat-main-row">
        <div className="chat-main-col">
      {/* ── Empty state: no store selected ── */}
      {!hasStore ? (
        <div className="empty-state">
          <div className="empty-icon">
            <BookOpen size={26} />
          </div>
          <div className="empty-title">選擇左側知識庫開始對話</div>
          <div className="empty-sub">
            選擇一個已有的知識庫，或新增新知識庫，系統就會自動建立 RAG 對話工作階段。
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
            {quickPromptsLoading
              ? '正在載入常見問題…'
              : quickPrompts.length > 0
                ? '知識庫已就緒，可以直接提問或點選常見問題：'
                : quickPromptsMessage || '目前沒有可用的常見問題，仍可直接輸入問題。'}
          </div>
          {quickPrompts.length > 0 && (
            <div className="welcome-chips">
            {quickPrompts.map((prompt) => (
              <button
                key={prompt}
                className="welcome-chip"
                onClick={() => sendQuick(prompt)}
                disabled={disabled || loading}
              >
                {prompt}
              </button>
            ))}
            </div>
          )}
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
                        傳送
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
                            title="重新產生"
                          >
                            <RotateCcw size={12} /> 重新產生
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
                ? `向「${currentStoreName}」提問（Enter 傳送 · Shift+Enter 換行）...`
                : '請先選擇知識庫...'
            }
            disabled={disabled}
          />
          <button
            className="send-btn"
            onClick={handleSubmit}
            disabled={disabled || !input.trim() || loading}
            aria-label="傳送"
          >
            <Send />
          </button>
        </div>
      </div>
        </div>
        {hasStore && suggestSidebar}
        </div>
      )}
    </main>
  );
}
