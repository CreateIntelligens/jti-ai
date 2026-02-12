import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Search,
  MessageCircle,
  Clock,
  Download,
  Copy,
  Check,
  ChevronDown,
  ChevronRight,
  Trash2,
  Play,
} from 'lucide-react';
import { deleteConversation, fetchWithApiKey, getGeneralConversationDetail } from '../services/api';

interface ConversationEntry {
  _id: string;
  session_id: string;
  mode: 'jti' | 'general';
  turn_number?: number;
  timestamp: string;
  user_message: string;
  agent_response: string;
  tool_calls: Array<{
    tool_name?: string;
    tool?: string;
    arguments?: Record<string, any>;
    result?: Record<string, any>;
    execution_time_ms?: number;
  }>;
  session_snapshot?: {
    step?: string;
    quiz_progress?: string;
    color_scores?: Record<string, number>;
  };
  error?: string;
}

interface SessionSummary {
  session_id: string;
  first_message_time: string;
  last_message_time?: string;
  message_count: number;
  preview?: string;
}

interface Session {
  session_id: string;
  conversations: ConversationEntry[];
  first_message_time: string;
  total: number;
}

interface ConversationHistoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  sessionId?: string;
  storeName?: string;
  mode?: 'jti' | 'general';
  onResumeSession?: (sessionId: string, messages: Array<{ role: 'user' | 'assistant'; text: string }>) => void;
}

export default function ConversationHistoryModal({
  isOpen,
  onClose,
  sessionId,
  storeName,
  mode = 'jti',
  onResumeSession,
}: ConversationHistoryModalProps) {
  const { t } = useTranslation();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [filteredSessions, setFilteredSessions] = useState<SessionSummary[]>([]);
  const [expandedSessionId, setExpandedSessionId] = useState<string | null>(null);
  const [expandedTurnMap, setExpandedTurnMap] = useState<Record<string, number | null>>({});
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [detailCache, setDetailCache] = useState<Record<string, ConversationEntry[]>>({});
  const [detailLoading, setDetailLoading] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    console.log('[ConversationHistory] Modal opened - mode:', mode, 'sessionId:', sessionId, 'storeName:', storeName);

    const fetchConversations = async () => {
      try {
        setLoading(true);
        setDetailCache({});

        let url = '';
        if (mode === 'jti') {
          url = `/api/jti/history`;
        } else {
          url = `/api/chat/history${storeName ? `?store_name=${encodeURIComponent(storeName)}` : ''}`;
        }

        console.log('[ConversationHistory] Fetching:', url);

        const response = await fetchWithApiKey(url);
        if (!response.ok) {
          console.error('[ConversationHistory] API Error:', response.status, response.statusText);
          throw new Error('Failed to fetch conversations');
        }

        const data = await response.json();
        console.log('[ConversationHistory] Received:', data.total_sessions, 'sessions,', data.total_conversations, 'conversations');

        const sessionsList = data.sessions || [];
        setSessions(sessionsList);
        setFilteredSessions(sessionsList);

        if (sessionId && sessionsList.some((s: SessionSummary) => s.session_id === sessionId)) {
          setExpandedSessionId(sessionId);
        }
      } catch (error) {
        console.error('[ConversationHistory] Error:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchConversations();
  }, [isOpen, sessionId, storeName, mode]);

  useEffect(() => {
    if (!isOpen) return;

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };

    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (!searchQuery.trim()) {
      setFilteredSessions(sessions);
      return;
    }

    const query = searchQuery.toLowerCase();

    if (mode === 'general') {
      // General 模式：搜 preview 和 session_id
      const filtered = sessions.filter((session) => {
        return (
          (session.preview && session.preview.toLowerCase().includes(query)) ||
          session.session_id.toLowerCase().includes(query)
        );
      });
      setFilteredSessions(filtered);
    } else {
      // JTI 模式：搜完整對話內容（sessions 帶 conversations）
      const filtered = (sessions as unknown as Session[])
        .map((session) => {
          const matchedConversations = session.conversations.filter((conv) => {
            return (
              conv.user_message.toLowerCase().includes(query) ||
              conv.agent_response.toLowerCase().includes(query) ||
              conv.tool_calls?.some(
                (tc) =>
                  (tc.tool_name || tc.tool || '').toLowerCase().includes(query) ||
                  JSON.stringify(tc.result || {}).toLowerCase().includes(query)
              )
            );
          });

          if (matchedConversations.length > 0) {
            return {
              ...session,
              conversations: matchedConversations,
              total: matchedConversations.length,
            };
          }
          return null;
        })
        .filter((s): s is Session => s !== null);

      setFilteredSessions(filtered as unknown as SessionSummary[]);
    }
  }, [searchQuery, sessions, mode]);

  const handleExpandSession = async (sid: string) => {
    if (expandedSessionId === sid) {
      setExpandedSessionId(null);
      return;
    }
    setExpandedSessionId(sid);

    // General 模式：按需載入完整對話
    if (mode === 'general' && !detailCache[sid]) {
      setDetailLoading(sid);
      try {
        const data = await getGeneralConversationDetail(sid);
        setDetailCache((prev) => ({ ...prev, [sid]: data.conversations || [] }));
      } catch (error) {
        console.error('[ConversationHistory] Failed to load detail:', error);
      } finally {
        setDetailLoading(null);
      }
    }
  };

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const exportAsJSON = async (sessionIds?: string[]) => {
    try {
      let url = '';
      if (mode === 'jti') {
        url = `/api/jti/history/export`;
        if (sessionIds && sessionIds.length > 0) {
          url += `?session_ids=${sessionIds.join(',')}`;
        }
      } else {
        url = `/api/chat/history/export`;
        if (storeName) {
          url += `?store_name=${encodeURIComponent(storeName)}`;
        }
        if (sessionIds && sessionIds.length > 0) {
          url += `${storeName ? '&' : '?'}session_ids=${sessionIds.join(',')}`;
        }
      }

      const response = await fetchWithApiKey(url);
      if (!response.ok) {
        throw new Error('Failed to export conversations');
      }

      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;

      const filename = sessionIds && sessionIds.length === 1
        ? `conversation-${sessionIds[0].substring(0, 8)}-${Date.now()}.json`
        : `conversations-${mode}-${Date.now()}.json`;

      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(downloadUrl);
    } catch (error) {
      console.error('[ConversationHistory] Export error:', error);
      alert('匯出失敗，請稍後再試');
    }
  };

  const handleDeleteSession = async (sid: string) => {
    if (!window.confirm(t('confirm_delete_session'))) return;

    try {
      await deleteConversation(mode, sid);

      const updated = sessions.filter((s) => s.session_id !== sid);
      setSessions(updated);
      // filteredSessions will be updated by the searchQuery useEffect

      if (expandedSessionId === sid) {
        setExpandedSessionId(null);
      }

      console.log('[ConversationHistory] Deleted session:', sid);
    } catch (error) {
      console.error('[ConversationHistory] Delete error:', error);
      alert('刪除失敗，請稍後再試');
    }
  };

  const formatTime = (timestamp: string) => {
    try {
      return new Date(timestamp).toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
    } catch {
      return timestamp;
    }
  };

  if (!isOpen) return null;

  return (
    <div className="conversation-history-overlay" onClick={onClose}>
      <div className="conversation-history-modal" onClick={(e) => e.stopPropagation()}>

        {/* Header */}
        <div className="conversation-header">
          <div className="conversation-header-left">
            <div className="conversation-header-icon">
              <MessageCircle size={24} />
            </div>
            <div>
              <h2>{t('conversation_history')}</h2>
              <p className="conversation-header-subtitle">
                {mode === 'jti' ? 'JTI Quiz Sessions' : `${t('knowledge_base') || '知識庫'}：${storeName || 'All'}`}
              </p>
            </div>
          </div>
          <button className="secondary" onClick={onClose} aria-label={t('close')}>
            {t('close')}
          </button>
        </div>

        {/* Toolbar */}
        <div className="conversation-toolbar">
          <div className="conversation-search-wrapper">
            <Search size={18} />
            <input
              type="text"
              placeholder={t('search_conversations')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <button
            onClick={() => exportAsJSON()}
            disabled={filteredSessions.length === 0}
          >
            <Download size={16} />
            {t('export')}
          </button>
        </div>

        {/* Content */}
        <div className="conversation-list">
          {loading ? (
            <div className="conversation-empty">
              <div>
                <div className="conversation-spinner" />
                <p>{t('loading')}</p>
              </div>
            </div>
          ) : filteredSessions.length === 0 ? (
            <div className="conversation-empty">
              <div>
                <MessageCircle size={52} strokeWidth={1.5} />
                <p>{searchQuery ? t('no_results_found') : t('no_conversations')}</p>
              </div>
            </div>
          ) : (
            filteredSessions.map((session, sessionIndex) => {
              const isSessionExpanded = expandedSessionId === session.session_id;
              const sessionTurnMap = expandedTurnMap[session.session_id] ?? null;
              const msgCount = (session as SessionSummary).message_count ?? (session as unknown as Session).total ?? 0;

              // 取得展開時的 conversations：general 模式用 detailCache，JTI 用 session 自帶的
              const conversations: ConversationEntry[] = mode === 'general'
                ? (detailCache[session.session_id] || [])
                : ((session as unknown as Session).conversations || []);

              return (
                <div
                  key={session.session_id || sessionIndex}
                  className={`session-card${isSessionExpanded ? ' expanded' : ''}`}
                >
                  {/* Session header */}
                  <div className="session-card-header">
                    <button
                      className="session-card-toggle"
                      onClick={() => handleExpandSession(session.session_id)}
                    >
                      <div style={{ flex: 1 }}>
                        <div className="session-card-meta">
                          <span className="session-badge">Session {sessionIndex + 1}</span>
                          <span className="session-count">{msgCount} {t('conversations_count')}</span>
                          <span className="session-time">
                            <Clock size={13} />
                            {formatTime(session.first_message_time)}
                          </span>
                        </div>
                        {mode === 'general' && (session as SessionSummary).preview && (
                          <p className="session-preview">{(session as SessionSummary).preview}</p>
                        )}
                        <p className="session-id">ID: {session.session_id.substring(0, 24)}...</p>
                      </div>
                      <div className="session-card-chevron">
                        {isSessionExpanded
                          ? <ChevronDown size={22} strokeWidth={2.5} />
                          : <ChevronRight size={22} strokeWidth={2.5} />
                        }
                      </div>
                    </button>

                    <div className="session-card-actions">
                      {onResumeSession && (
                        <button
                          onClick={async (e) => {
                            e.stopPropagation();
                            // General 模式：確保已載入完整對話
                            let convs = conversations;
                            if (mode === 'general' && !detailCache[session.session_id]) {
                              try {
                                const data = await getGeneralConversationDetail(session.session_id);
                                convs = data.conversations || [];
                                setDetailCache((prev) => ({ ...prev, [session.session_id]: convs }));
                              } catch (error) {
                                console.error('[ConversationHistory] Failed to load for resume:', error);
                                return;
                              }
                            }
                            const messages = convs.flatMap((conv) => [
                              { role: 'user' as const, text: conv.user_message },
                              { role: 'assistant' as const, text: conv.agent_response },
                            ]);
                            onResumeSession(session.session_id, messages);
                            onClose();
                          }}
                          title={t('resume_session')}
                        >
                          <Play size={16} />
                        </button>
                      )}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          exportAsJSON([session.session_id]);
                        }}
                        title={t('export')}
                      >
                        <Download size={16} />
                      </button>
                      <button
                        className="session-delete-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteSession(session.session_id);
                        }}
                        title={t('delete')}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>

                  {/* Expanded conversations */}
                  {isSessionExpanded && (
                    <div className="session-conversations">
                      {detailLoading === session.session_id ? (
                        <div className="conversation-empty" style={{ padding: '2rem' }}>
                          <div>
                            <div className="conversation-spinner" />
                            <p>{t('loading')}</p>
                          </div>
                        </div>
                      ) : conversations.map((conv, convIndex) => {
                        const turnNum = conv.turn_number || convIndex + 1;
                        const isTurnExpanded = sessionTurnMap === turnNum;

                        return (
                          <div
                            key={conv._id || convIndex}
                            className={`turn-card${isTurnExpanded ? ' expanded' : ''}`}
                          >
                            <button
                              className="turn-card-toggle"
                              onClick={() => setExpandedTurnMap(prev => ({
                                ...prev,
                                [session.session_id]: isTurnExpanded ? null : turnNum
                              }))}
                            >
                              <div style={{ flex: 1 }}>
                                <div className="turn-card-meta">
                                  <span className="turn-badge">#{turnNum}</span>
                                  <span className="session-time">
                                    <Clock size={12} />
                                    {formatTime(conv.timestamp)}
                                  </span>
                                </div>
                                <p className={`turn-user-msg${isTurnExpanded ? '' : ' clamped'}`}>
                                  <span className="turn-user-label">{t('you') || '您'}：</span>{' '}
                                  {conv.user_message}
                                </p>
                              </div>
                              <div className="turn-card-chevron">
                                {isTurnExpanded
                                  ? <ChevronDown size={18} strokeWidth={2.5} />
                                  : <ChevronRight size={18} strokeWidth={2.5} />
                                }
                              </div>
                            </button>

                            {isTurnExpanded && (
                              <div className="turn-detail">
                                {/* AI Response */}
                                <div className="turn-detail-label">AI {t('response') || '回應'}</div>
                                <div className="turn-detail-response">
                                  <p>{conv.agent_response}</p>
                                  <button
                                    className="secondary small copy-btn"
                                    onClick={() => copyToClipboard(conv.agent_response, `agent-${conv._id}`)}
                                  >
                                    {copiedId === `agent-${conv._id}` ? (
                                      <><Check size={14} /> {t('copied')}</>
                                    ) : (
                                      <><Copy size={14} /> {t('copy')}</>
                                    )}
                                  </button>
                                </div>

                                {/* Tool Calls */}
                                {conv.tool_calls && conv.tool_calls.length > 0 && (
                                  <div>
                                    <div className="turn-tool-calls-label">
                                      Tool Calls ({conv.tool_calls.length})
                                    </div>
                                    {conv.tool_calls.slice(0, 3).map((tool, toolIndex) => (
                                      <div key={toolIndex} className="turn-tool-card">
                                        <div className="turn-tool-name">
                                          {tool.tool_name || tool.tool || 'unknown'}
                                        </div>
                                        {tool.execution_time_ms && (
                                          <div className="turn-tool-time">{tool.execution_time_ms}ms</div>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div className="conversation-footer">
          <div className="conversation-footer-stats">
            <span>
              Sessions: <span className="stat-value">{filteredSessions.length}</span>
            </span>
            <span className="stat-sep">|</span>
            <span>
              {t('total_conversations')}: <span className="stat-value">
                {filteredSessions.reduce((sum, s) => sum + ((s as SessionSummary).message_count ?? (s as unknown as Session).total ?? 0), 0)}
              </span> {t('conversations_count')}
            </span>
            {searchQuery && (
              <>
                <span className="stat-sep">|</span>
                <span>
                  （{t('filtered')} {sessions.length} sessions，{sessions.reduce((sum, s) => sum + ((s as SessionSummary).message_count ?? (s as unknown as Session).total ?? 0), 0)} {t('conversations_count')}）
                </span>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
