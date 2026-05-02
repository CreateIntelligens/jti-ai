import { useEffect, useState } from 'react';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import AdminPanel from './components/AdminPanel';
import ApiKeysPanel from './components/ApiKeysPanel';
import PromptPanel from './components/PromptPanel';
import ExtKeysPanel from './components/ExtKeysPanel';
import ConversationHistoryModal from './components/ConversationHistoryModal';
import Jti from './pages/Jti';
import Hciot from './pages/Hciot';
import { useAppChat } from './hooks/useAppChat';
import { PROJECT_COLORS, getStoreIcon } from './utils/storeDisplay';
import './styles/shared/index.css';
import './styles/app/layout.css';
import './styles/app/forms.css';
import './styles/app/components.css';
import './styles/app/messages.css';
import './styles/app/light.css';
import './styles/app/variables.css';
import './styles/app/redesign.css';
import './styles/conversation-history.css';

type PanelId = 'admin' | 'apikeys' | 'prompt' | 'extkeys' | null;

export default function App() {
  // 受限 hostname（外網 domain）只顯示 ALLOWED_PAGES；其餘顯示全部
  const restrictedHosts = (import.meta.env.VITE_PUBLIC_RESTRICTED_HOSTS || '')
    .split(',').map((s: string) => s.trim().toLowerCase()).filter(Boolean);
  const isRestricted = restrictedHosts.includes(window.location.hostname.toLowerCase());

  const allowedPages = (import.meta.env.VITE_PUBLIC_ALLOWED_PAGES || 'jti')
    .split(',').map((s: string) => s.trim().toLowerCase());
  const canShow = (p: string) => !isRestricted || allowedPages.includes(p);

  const pathname = window.location.pathname;
  const page = pathname.replace(/^\/+|\/+$/g, '').toLowerCase() || 'home';

  const isHciotPage = page === 'hciot' && canShow('hciot');
  const isJtiPage = page === 'jti' && canShow('jti');

  useEffect(() => {
    if (isHciotPage && pathname !== '/hciot') window.history.replaceState(null, '', '/hciot');
    else if (isJtiPage && pathname !== '/jti') window.history.replaceState(null, '', '/jti');
  }, [isHciotPage, isJtiPage, pathname]);

  if (isHciotPage) return <Hciot />;
  if (isJtiPage) return <Jti />;

  const {
    sidebarOpen,
    conversationHistoryModalOpen, setConversationHistoryModalOpen,
    status, stores, keyNames,
    knowledgeTargets, currentTarget, currentTargetId, currentStore,
    files, filesLoading,
    messages, setMessages,
    loading,
    sessionId, setSessionId,
    theme, toggleTheme,
    toggleSidebar, showStatus,
    refreshStores, handleRefreshKnowledge,
    handleStoreChange, handleRestartChat,
    handleCreateStore, handleDeleteStore,
    handleUploadFile, handleDeleteFile,
    handleSendMessage, handleRegenerate, handleEditAndResend,
  } = useAppChat();

  const [panel, setPanel] = useState<PanelId>(null);
  const openPanel = (id: PanelId) => setPanel(id);
  const closePanel = () => setPanel(null);

  // Derive store display info for chat area
  const activeStore = currentTarget?.kind === 'store'
    ? stores.find((s) => s.name === currentTarget.storeName)
    : null;
  const currentStoreName = activeStore ? (activeStore.display_name || activeStore.name) : null;
  const currentStoreIcon = getStoreIcon(activeStore?.managed_app || '');
  const currentProjectIdx = typeof activeStore?.key_index === 'number' ? activeStore.key_index : 0;
  const currentProjectName = keyNames.length > 1
    ? (keyNames[currentProjectIdx] || `Key #${currentProjectIdx + 1}`)
    : null;
  const currentProjectColor = PROJECT_COLORS[currentProjectIdx % PROJECT_COLORS.length];

  return (
    <>
      <div className="app-shell">
        <Header
          sidebarOpen={sidebarOpen}
          onToggleSidebar={toggleSidebar}
          status={status}
          theme={theme}
          onToggleTheme={toggleTheme}
          canOpenConversationHistory={Boolean(currentStore)}
          onOpenConversationHistory={() => setConversationHistoryModalOpen(true)}
          onOpenAdminPanel={() => openPanel('admin')}
          onOpenApiKeysPanel={() => openPanel('apikeys')}
          onOpenPromptPanel={() => openPanel('prompt')}
          onOpenExtKeysPanel={() => openPanel('extkeys')}
          onShowStatus={showStatus}
        />
        <div className="app-body">
          <Sidebar
            isOpen={sidebarOpen}
            stores={stores}
            keyNames={keyNames}
            knowledgeTargets={knowledgeTargets}
            currentTargetId={currentTargetId}
            files={files}
            filesLoading={filesLoading}
            onTargetChange={handleStoreChange}
            onUploadFile={handleUploadFile}
            onDeleteFile={handleDeleteFile}
            onCreateStore={handleCreateStore}
          />
          <ChatArea
            messages={messages}
            onSendMessage={handleSendMessage}
            disabled={!currentStore}
            loading={loading}
            onRegenerate={handleRegenerate}
            onEditAndResend={handleEditAndResend}
            currentStoreName={currentStoreName}
            currentStoreIcon={currentStoreIcon}
            currentProjectName={currentProjectName}
            currentProjectColor={currentProjectColor}
            onOpenPromptPanel={() => openPanel('prompt')}
            onRestartChat={handleRestartChat}
            onOpenHistory={() => setConversationHistoryModalOpen(true)}
            onCreateStore={() => openPanel('admin')}
          />
        </div>
      </div>

      {/* ── Slide Panels ── */}
      <AdminPanel
        isOpen={panel === 'admin'}
        onClose={closePanel}
        stores={stores}
        currentStore={currentStore}
        onCreateStore={handleCreateStore}
        onDeleteStore={handleDeleteStore}
        onRefresh={refreshStores}
      />
      <ApiKeysPanel
        isOpen={panel === 'apikeys'}
        onClose={closePanel}
        onApiKeySaved={() => {
          showStatus('✅ API Key 已儲存');
          void handleRefreshKnowledge();
        }}
      />
      <PromptPanel
        isOpen={panel === 'prompt'}
        onClose={closePanel}
        currentStore={currentStore}
        currentStoreName={currentStoreName}
        onRestartChat={handleRestartChat}
        onShowStatus={showStatus}
      />
      <ExtKeysPanel
        isOpen={panel === 'extkeys'}
        onClose={closePanel}
        stores={stores}
        onShowStatus={showStatus}
      />

      {/* ── Conversation History (kept as modal) ── */}
      <ConversationHistoryModal
        isOpen={conversationHistoryModalOpen}
        onClose={() => setConversationHistoryModalOpen(false)}
        sessionId={sessionId || undefined}
        storeName={currentStore || undefined}
        mode="general"
        onResumeSession={(sid, msgs, _lang) => {
          setSessionId(sid);
          setMessages(msgs.map((m) => ({
            role: m.role === 'assistant' ? 'model' : m.role,
            text: m.text,
            turnNumber: m.turnNumber,
            citations: m.citations,
          })));
          // General 模式目前不處理語言切換（沒有多語言支援）
        }}
      />
    </>
  );
}
