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
} from 'lucide-react';

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
  storeName?: string;  // 用於 general mode，可選
  mode?: 'jti' | 'general';
}

export default function ConversationHistoryModal({
  isOpen,
  onClose,
  sessionId,
  storeName,
  mode = 'jti',
}: ConversationHistoryModalProps) {
  const { t } = useTranslation();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [filteredSessions, setFilteredSessions] = useState<Session[]>([]);
  const [expandedSessionId, setExpandedSessionId] = useState<string | null>(null);
  const [expandedTurnMap, setExpandedTurnMap] = useState<Record<string, number | null>>({});
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // 獲取對話歷史
  useEffect(() => {
    if (!isOpen) return;

    console.log('[ConversationHistory] Modal opened - mode:', mode, 'sessionId:', sessionId, 'storeName:', storeName);

    const fetchConversations = async () => {
      try {
        setLoading(true);

        // 根據 mode 使用不同的 API 端點
        let url = '';
        if (mode === 'jti') {
          // JTI 模式：查詢所有 JTI sessions
          url = `/api/jti/conversations?mode=${mode}`;
        } else {
          // General 模式：查詢特定知識庫的所有 sessions
          url = `/api/chat/conversations${storeName ? `?store_name=${encodeURIComponent(storeName)}` : ''}`;
        }

        console.log('[ConversationHistory] Fetching:', url);

        const response = await fetch(url);
        if (!response.ok) {
          console.error('[ConversationHistory] API Error:', response.status, response.statusText);
          throw new Error('Failed to fetch conversations');
        }

        const data = await response.json();
        console.log('[ConversationHistory] Received:', data.total_sessions, 'sessions,', data.total_conversations, 'conversations');

        const sessionsList = data.sessions || [];
        setSessions(sessionsList);
        setFilteredSessions(sessionsList);

        // 如果是當前 session，自動展開
        if (sessionId && sessionsList.some((s: Session) => s.session_id === sessionId)) {
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

  // ESC 鍵關閉 Modal
  useEffect(() => {
    if (!isOpen) return;

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose]);

  // 搜索對話
  useEffect(() => {
    if (!searchQuery.trim()) {
      setFilteredSessions(sessions);
      return;
    }

    const query = searchQuery.toLowerCase();
    const filtered = sessions
      .map((session) => {
        // 搜尋該 session 內的對話
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

        // 如果有匹配的對話，返回過濾後的 session
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

    setFilteredSessions(filtered);
  }, [searchQuery, sessions]);

  // 複製到剪貼板
  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  // 導出對話為 JSON（打 API）
  const exportAsJSON = async (sessionIds?: string[]) => {
    try {
      let url = '';
      if (mode === 'jti') {
        url = `/api/jti/conversations/export?mode=${mode}`;
        if (sessionIds && sessionIds.length > 0) {
          url += `&session_ids=${sessionIds.join(',')}`;
        }
      } else {
        url = `/api/chat/conversations/export`;
        if (storeName) {
          url += `?store_name=${encodeURIComponent(storeName)}`;
        }
        if (sessionIds && sessionIds.length > 0) {
          url += `${storeName ? '&' : '?'}session_ids=${sessionIds.join(',')}`;
        }
      }

      const response = await fetch(url);
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

  // 格式化時間
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
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(10, 13, 19, 0.92)',
        backdropFilter: 'blur(8px)',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '90%',
          maxWidth: '1100px',
          height: '88vh',
          display: 'flex',
          flexDirection: 'column',
          background: 'linear-gradient(180deg, rgba(18, 22, 30, 0.98) 0%, rgba(14, 18, 26, 0.96) 100%)',
          backdropFilter: 'blur(22px) saturate(160%)',
          border: '1px solid rgba(224, 192, 104, 0.2)',
          borderRadius: '16px',
          boxShadow: '0 24px 48px rgba(0, 0, 0, 0.7), inset 0 1px 0 rgba(224, 192, 104, 0.1)',
          overflow: 'hidden',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 標題欄 */}
        <div
          style={{
            padding: '24px 32px',
            borderBottom: '1px solid rgba(224, 192, 104, 0.15)',
            background: 'linear-gradient(180deg, rgba(224, 192, 104, 0.03), transparent)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div
              style={{
                width: '52px',
                height: '52px',
                borderRadius: '14px',
                background: 'linear-gradient(135deg, rgba(224, 192, 104, 0.15), rgba(205, 127, 50, 0.1))',
                border: '1px solid rgba(224, 192, 104, 0.25)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <MessageCircle size={26} style={{ color: '#e0c068', strokeWidth: 2 }} />
            </div>
            <div>
              <h2
                style={{
                  margin: 0,
                  fontSize: '26px',
                  fontFamily: "'Cormorant Garamond', serif",
                  fontWeight: 700,
                  color: '#f2dca2',
                  letterSpacing: '0.02em',
                }}
              >
                {t('conversation_history')}
              </h2>
              <p
                style={{
                  margin: '4px 0 0 0',
                  fontSize: '13px',
                  color: '#94a3b8',
                  fontFamily: "'Inter', sans-serif",
                }}
              >
                {mode === 'jti' ? 'JTI Quiz Sessions' : `知識庫：${storeName || 'All'}`}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              minWidth: '96px',
              height: '44px',
              padding: '0 14px',
              gap: '8px',
              borderRadius: '12px',
              background: 'linear-gradient(180deg, rgba(24, 28, 38, 0.7), rgba(16, 19, 28, 0.6))',
              border: '1px solid rgba(224, 192, 104, 0.2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#e0c068',
              fontSize: '13px',
              fontWeight: 600,
              fontFamily: "'Noto Sans TC', 'PingFang TC', 'Microsoft JhengHei', 'Inter', sans-serif",
              cursor: 'pointer',
              transition: 'all 0.28s cubic-bezier(0.16, 1, 0.3, 1)',
            }}
            aria-label={t('close') || 'Close'}
            onMouseEnter={(e) => {
              const target = e.currentTarget;
              target.style.background = 'linear-gradient(180deg, rgba(34, 38, 50, 0.8), rgba(18, 22, 30, 0.7))';
              target.style.borderColor = 'rgba(224, 192, 104, 0.4)';
              target.style.transform = 'translateY(-2px)';
            }}
            onMouseLeave={(e) => {
              const target = e.currentTarget;
              target.style.background = 'linear-gradient(180deg, rgba(24, 28, 38, 0.7), rgba(16, 19, 28, 0.6))';
              target.style.borderColor = 'rgba(224, 192, 104, 0.2)';
              target.style.transform = 'translateY(0)';
            }}
          >
            <span aria-hidden style={{ fontSize: '18px', lineHeight: 1 }}>X</span>
            <span>{t('close') || 'Close'}</span>
          </button>
        </div>

        {/* 搜索和工具欄 */}
        <div
          style={{
            padding: '18px 32px',
            borderBottom: '1px solid rgba(224, 192, 104, 0.1)',
            display: 'flex',
            gap: '12px',
          }}
        >
          <div style={{ flex: 1, position: 'relative' }}>
            <Search
              size={18}
              style={{
                position: 'absolute',
                left: '16px',
                top: '50%',
                transform: 'translateY(-50%)',
                color: '#94a3b8',
              }}
            />
            <input
              type="text"
              placeholder={t('search_conversations')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                width: '100%',
                padding: '0 18px 0 48px',
                height: '48px',
                background: 'linear-gradient(180deg, rgba(24, 28, 38, 0.6), rgba(16, 19, 28, 0.5))',
                border: '1px solid rgba(224, 192, 104, 0.2)',
                borderRadius: '999px',
                color: '#e8eaed',
                fontSize: '14px',
                fontFamily: "'Inter', sans-serif",
                outline: 'none',
                transition: 'all 0.28s',
              }}
              onFocus={(e) => {
                e.target.style.borderColor = 'rgba(224, 192, 104, 0.4)';
                e.target.style.boxShadow = '0 0 0 3px rgba(224, 192, 104, 0.1)';
              }}
              onBlur={(e) => {
                e.target.style.borderColor = 'rgba(224, 192, 104, 0.2)';
                e.target.style.boxShadow = 'none';
              }}
            />
          </div>
          <button
            onClick={exportAsJSON}
            disabled={filteredSessions.length === 0}
            style={{
              padding: '0 26px',
              height: '48px',
              background: filteredSessions.length === 0
                ? 'rgba(224, 192, 104, 0.1)'
                : 'linear-gradient(135deg, #e0c068, #d4a843)',
              border: '1px solid rgba(224, 192, 104, 0.35)',
              borderRadius: '999px',
              color: filteredSessions.length === 0 ? '#94a3b8' : '#1a1f2e',
              fontSize: '14px',
              fontWeight: 600,
              fontFamily: "'Inter', sans-serif",
              cursor: filteredSessions.length === 0 ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              transition: 'all 0.28s',
              opacity: filteredSessions.length === 0 ? 0.5 : 1,
            }}
            onMouseEnter={(e) => {
              if (filteredSessions.length > 0) {
                e.currentTarget.style.transform = 'translateY(-2px)';
                e.currentTarget.style.boxShadow = '0 8px 20px rgba(224, 192, 104, 0.3)';
              }
            }}
            onMouseLeave={(e) => {
              if (filteredSessions.length > 0) {
                e.currentTarget.style.transform = 'translateY(0)';
                e.currentTarget.style.boxShadow = 'none';
              }
            }}
          >
            <Download size={16} />
            {t('export')}
          </button>
        </div>

        {/* 對話列表 */}
        <div
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '24px 32px',
          }}
        >
          {loading ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
              <div style={{ textAlign: 'center' }}>
                <div
                  style={{
                    width: '52px',
                    height: '52px',
                    border: '4px solid rgba(224, 192, 104, 0.2)',
                    borderTopColor: '#e0c068',
                    borderRadius: '50%',
                    animation: 'spin 1s linear infinite',
                    margin: '0 auto 20px',
                  }}
                ></div>
                <p style={{ margin: 0, color: '#94a3b8', fontFamily: "'Inter', sans-serif", fontSize: '15px' }}>
                  {t('loading')}
                </p>
              </div>
            </div>
          ) : filteredSessions.length === 0 ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
              <div style={{ textAlign: 'center' }}>
                <MessageCircle
                  size={56}
                  style={{
                    color: 'rgba(224, 192, 104, 0.25)',
                    strokeWidth: 1.5,
                    margin: '0 auto 20px'
                  }}
                />
                <p style={{ margin: 0, color: '#94a3b8', fontFamily: "'Inter', sans-serif", fontSize: '15px' }}>
                  {searchQuery ? t('no_results_found') : t('no_conversations')}
                </p>
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {filteredSessions.map((session, sessionIndex) => {
                const isSessionExpanded = expandedSessionId === session.session_id;
                const sessionTurnMap = expandedTurnMap[session.session_id] ?? null;

                return (
                  <div
                    key={session.session_id || sessionIndex}
                    style={{
                      background: 'linear-gradient(180deg, rgba(24, 28, 38, 0.5), rgba(16, 19, 28, 0.4))',
                      border: '2px solid rgba(224, 192, 104, 0.2)',
                      borderRadius: '16px',
                      overflow: 'hidden',
                      transition: 'all 0.28s',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.borderColor = 'rgba(224, 192, 104, 0.35)';
                      e.currentTarget.style.background = 'linear-gradient(180deg, rgba(24, 28, 38, 0.6), rgba(16, 19, 28, 0.5))';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = 'rgba(224, 192, 104, 0.2)';
                      e.currentTarget.style.background = 'linear-gradient(180deg, rgba(24, 28, 38, 0.5), rgba(16, 19, 28, 0.4))';
                    }}
                  >
                    {/* Session 摘要 */}
                    <div style={{ display: 'flex', alignItems: 'stretch' }}>
                      <button
                        onClick={() => setExpandedSessionId(isSessionExpanded ? null : session.session_id)}
                        style={{
                          flex: 1,
                          padding: '20px 24px',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          cursor: 'pointer',
                          background: 'transparent',
                          border: 'none',
                          textAlign: 'left',
                        }}
                      >
                        <div style={{ flex: 1 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '10px' }}>
                            <span
                              style={{
                                padding: '6px 16px',
                                background: 'linear-gradient(135deg, rgba(224, 192, 104, 0.2), rgba(205, 127, 50, 0.15))',
                                border: '1px solid rgba(224, 192, 104, 0.35)',
                                borderRadius: '999px',
                                color: '#e0c068',
                                fontSize: '13px',
                                fontWeight: 700,
                                fontFamily: "'Inter', sans-serif",
                              }}
                            >
                              Session {sessionIndex + 1}
                            </span>
                            <span
                              style={{
                                padding: '6px 14px',
                                background: 'rgba(100, 116, 139, 0.15)',
                                border: '1px solid rgba(148, 163, 184, 0.25)',
                                borderRadius: '999px',
                                color: '#94a3b8',
                                fontSize: '12px',
                                fontWeight: 600,
                                fontFamily: "'Inter', sans-serif",
                              }}
                            >
                              {session.total} 則對話
                            </span>
                            <span
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '6px',
                                color: '#94a3b8',
                                fontSize: '12px',
                                fontFamily: "'Inter', sans-serif",
                              }}
                            >
                              <Clock size={13} />
                              {formatTime(session.first_message_time)}
                            </span>
                          </div>
                          <p
                            style={{
                              margin: 0,
                              color: '#64748b',
                              fontSize: '13px',
                              fontFamily: "'JetBrains Mono', monospace",
                              letterSpacing: '-0.02em',
                            }}
                          >
                            ID: {session.session_id.substring(0, 24)}...
                          </p>
                        </div>
                        <div style={{ marginLeft: '16px', flexShrink: 0 }}>
                          {isSessionExpanded ? (
                            <ChevronDown size={24} style={{ color: '#e0c068', strokeWidth: 2.5 }} />
                          ) : (
                            <ChevronRight size={24} style={{ color: '#94a3b8', strokeWidth: 2.5 }} />
                          )}
                        </div>
                      </button>

                      {/* 匯出單個 session 按鈕 */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          exportAsJSON([session.session_id]);
                        }}
                        style={{
                          padding: '0 20px',
                          background: 'rgba(224, 192, 104, 0.1)',
                          border: 'none',
                          borderLeft: '1px solid rgba(224, 192, 104, 0.15)',
                          color: '#e0c068',
                          fontSize: '13px',
                          fontWeight: 600,
                          fontFamily: "'Inter', sans-serif",
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px',
                          transition: 'all 0.2s',
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.background = 'rgba(224, 192, 104, 0.15)';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.background = 'rgba(224, 192, 104, 0.1)';
                        }}
                        title="匯出此對話"
                      >
                        <Download size={16} />
                      </button>
                    </div>

                    {/* 展開 Session 內的對話列表 */}
                    {isSessionExpanded && (
                      <div
                        style={{
                          borderTop: '1px solid rgba(224, 192, 104, 0.15)',
                          padding: '16px',
                          background: 'rgba(10, 13, 19, 0.3)',
                        }}
                      >
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                          {session.conversations.map((conv, convIndex) => {
                            const turnNum = conv.turn_number || convIndex + 1;
                            const isTurnExpanded = sessionTurnMap === turnNum;

                            return (
                              <div
                                key={conv._id || convIndex}
                                style={{
                                  background: 'linear-gradient(180deg, rgba(24, 28, 38, 0.6), rgba(16, 19, 28, 0.5))',
                                  border: '1px solid rgba(224, 192, 104, 0.12)',
                                  borderRadius: '12px',
                                  overflow: 'hidden',
                                  transition: 'all 0.24s',
                                }}
                                onMouseEnter={(e) => {
                                  e.currentTarget.style.borderColor = 'rgba(224, 192, 104, 0.25)';
                                }}
                                onMouseLeave={(e) => {
                                  e.currentTarget.style.borderColor = 'rgba(224, 192, 104, 0.12)';
                                }}
                              >
                                {/* 對話摘要 */}
                                <button
                                  onClick={() => setExpandedTurnMap(prev => ({
                                    ...prev,
                                    [session.session_id]: isTurnExpanded ? null : turnNum
                                  }))}
                                  style={{
                                    width: '100%',
                                    padding: '16px 20px',
                                    display: 'flex',
                                    alignItems: 'flex-start',
                                    justifyContent: 'space-between',
                                    cursor: 'pointer',
                                    background: 'transparent',
                                    border: 'none',
                                    textAlign: 'left',
                                  }}
                                >
                                  <div style={{ flex: 1 }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '10px' }}>
                                      <span
                                        style={{
                                          padding: '4px 12px',
                                          background: 'linear-gradient(135deg, rgba(224, 192, 104, 0.15), rgba(205, 127, 50, 0.1))',
                                          border: '1px solid rgba(224, 192, 104, 0.28)',
                                          borderRadius: '999px',
                                          color: '#e0c068',
                                          fontSize: '11.5px',
                                          fontWeight: 700,
                                          fontFamily: "'Inter', sans-serif",
                                        }}
                                      >
                                        #{turnNum}
                                      </span>
                                      <span
                                        style={{
                                          display: 'flex',
                                          alignItems: 'center',
                                          gap: '5px',
                                          color: '#94a3b8',
                                          fontSize: '11.5px',
                                          fontFamily: "'Inter', sans-serif",
                                        }}
                                      >
                                        <Clock size={12} />
                                        {formatTime(conv.timestamp)}
                                      </span>
                                    </div>
                                    <p
                                      style={{
                                        margin: 0,
                                        color: '#e8eaed',
                                        fontSize: '14px',
                                        fontFamily: "'Inter', sans-serif",
                                        lineHeight: '1.6',
                                        overflow: 'hidden',
                                        textOverflow: 'ellipsis',
                                        display: '-webkit-box',
                                        WebkitLineClamp: isTurnExpanded ? 'unset' : 2,
                                        WebkitBoxOrient: 'vertical',
                                      }}
                                    >
                                      <span style={{ color: '#e0c068', fontWeight: 600 }}>您：</span>{' '}
                                      {conv.user_message}
                                    </p>
                                  </div>
                                  <div style={{ marginLeft: '14px', flexShrink: 0 }}>
                                    {isTurnExpanded ? (
                                      <ChevronDown size={20} style={{ color: '#e0c068', strokeWidth: 2.5 }} />
                                    ) : (
                                      <ChevronRight size={20} style={{ color: '#94a3b8', strokeWidth: 2.5 }} />
                                    )}
                                  </div>
                                </button>

                                {/* 展開對話詳細內容 */}
                                {isTurnExpanded && (
                                  <div
                                    style={{
                                      borderTop: '1px solid rgba(224, 192, 104, 0.1)',
                                      padding: '20px',
                                      background: 'rgba(10, 13, 19, 0.5)',
                                    }}
                                  >
                                    {/* AI 回應 */}
                                    <div style={{ marginBottom: '20px' }}>
                                      <div
                                        style={{
                                          color: '#e0c068',
                                          fontSize: '12.5px',
                                          fontWeight: 600,
                                          fontFamily: "'Inter', sans-serif",
                                          marginBottom: '10px',
                                        }}
                                      >
                                        AI 回應
                                      </div>
                                      <div
                                        style={{
                                          background: 'linear-gradient(135deg, rgba(224, 192, 104, 0.06), rgba(205, 127, 50, 0.03))',
                                          border: '1px solid rgba(224, 192, 104, 0.15)',
                                          borderRadius: '10px',
                                          padding: '16px',
                                        }}
                                      >
                                        <p
                                          style={{
                                            margin: 0,
                                            color: '#e8eaed',
                                            fontSize: '14px',
                                            fontFamily: "'Inter', sans-serif",
                                            lineHeight: '1.7',
                                            whiteSpace: 'pre-wrap',
                                            wordBreak: 'break-word',
                                          }}
                                        >
                                          {conv.agent_response}
                                        </p>
                                        <button
                                          onClick={() => copyToClipboard(conv.agent_response, `agent-${conv._id}`)}
                                          style={{
                                            marginTop: '12px',
                                            padding: '7px 14px',
                                            background: 'rgba(224, 192, 104, 0.1)',
                                            border: '1px solid rgba(224, 192, 104, 0.25)',
                                            borderRadius: '8px',
                                            color: '#e0c068',
                                            fontSize: '12px',
                                            fontWeight: 500,
                                            fontFamily: "'Inter', sans-serif",
                                            cursor: 'pointer',
                                            display: 'inline-flex',
                                            alignItems: 'center',
                                            gap: '6px',
                                            transition: 'all 0.2s',
                                          }}
                                          onMouseEnter={(e) => {
                                            e.currentTarget.style.background = 'rgba(224, 192, 104, 0.15)';
                                          }}
                                          onMouseLeave={(e) => {
                                            e.currentTarget.style.background = 'rgba(224, 192, 104, 0.1)';
                                          }}
                                        >
                                          {copiedId === `agent-${conv._id}` ? (
                                            <>
                                              <Check size={14} /> {t('copied')}
                                            </>
                                          ) : (
                                            <>
                                              <Copy size={14} /> {t('copy')}
                                            </>
                                          )}
                                        </button>
                                      </div>
                                    </div>

                                    {/* 工具呼叫 */}
                                    {conv.tool_calls && conv.tool_calls.length > 0 && (
                                      <div>
                                        <div
                                          style={{
                                            color: '#cd7f32',
                                            fontSize: '12.5px',
                                            fontWeight: 600,
                                            fontFamily: "'Inter', sans-serif",
                                            marginBottom: '10px',
                                          }}
                                        >
                                          🔧 工具呼叫 ({conv.tool_calls.length})
                                        </div>
                                        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                                          {conv.tool_calls.slice(0, 3).map((tool, toolIndex) => (
                                            <div
                                              key={toolIndex}
                                              style={{
                                                background: 'rgba(205, 127, 50, 0.08)',
                                                border: '1px solid rgba(205, 127, 50, 0.2)',
                                                borderRadius: '8px',
                                                padding: '12px',
                                              }}
                                            >
                                              <div
                                                style={{
                                                  fontFamily: "'JetBrains Mono', 'Courier New', monospace",
                                                  color: '#cd7f32',
                                                  fontSize: '13px',
                                                  fontWeight: 600,
                                                  marginBottom: tool.execution_time_ms ? '6px' : 0,
                                                }}
                                              >
                                                {tool.tool_name || tool.tool || 'unknown'}
                                              </div>
                                              {tool.execution_time_ms && (
                                                <div
                                                  style={{
                                                    color: '#94a3b8',
                                                    fontSize: '11.5px',
                                                  }}
                                                >
                                                  ⏱ {tool.execution_time_ms}ms
                                                </div>
                                              )}
                                            </div>
                                          ))}
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* 底部統計欄 */}
        <div
          style={{
            borderTop: '1px solid rgba(224, 192, 104, 0.15)',
            padding: '20px 32px',
            background: 'linear-gradient(180deg, transparent, rgba(224, 192, 104, 0.02))',
          }}
        >
          <div
            style={{
              color: '#94a3b8',
              fontSize: '14px',
              fontFamily: "'Inter', sans-serif",
              textAlign: 'center',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '20px',
            }}
          >
            <span>
              Sessions:{' '}
              <span style={{ color: '#e0c068', fontWeight: 600 }}>{filteredSessions.length}</span>
            </span>
            <span style={{ color: 'rgba(224, 192, 104, 0.3)' }}>|</span>
            <span>
              總對話數:{' '}
              <span style={{ color: '#e0c068', fontWeight: 600 }}>
                {filteredSessions.reduce((sum, s) => sum + s.total, 0)}
              </span>
            </span>
            {searchQuery && (
              <>
                <span style={{ color: 'rgba(224, 192, 104, 0.3)' }}>|</span>
                <span style={{ fontSize: '13px' }}>
                  （過濾自 {sessions.length} 個 session，{sessions.reduce((sum, s) => sum + s.total, 0)} 則對話）
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
