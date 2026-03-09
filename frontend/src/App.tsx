import Header from './components/Header';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import StoreManagementModal from './components/StoreManagementModal';
import PromptManagementModal from './components/PromptManagementModal';
import UserApiKeyModal from './components/UserApiKeyModal';
import ConversationHistoryModal from './components/ConversationHistoryModal';
import Jti from './pages/Jti';
import Hciot from './pages/Hciot';
import { useAppChat } from './hooks/useAppChat';
import * as api from './services/api';
import './styles/shared/index.css';
import './styles/app/layout.css';
import './styles/app/forms.css';
import './styles/app/components.css';
import './styles/app/messages.css';
import './styles/app/light.css';

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
  const activeGeminiKeyName = api.getActiveApiKeyName();

  if (isHciotPage) {
    if (pathname !== '/hciot') window.history.replaceState(null, '', '/hciot');
    return <Hciot />;
  }

  if (isJtiPage) {
    if (pathname !== '/jti') window.history.replaceState(null, '', '/jti');
    return <Jti />;
  }

  const {
    sidebarOpen,
    storeModalOpen, setStoreModalOpen,
    promptModalOpen, setPromptModalOpen,
    userApiKeyModalOpen, setUserApiKeyModalOpen,
    conversationHistoryModalOpen, setConversationHistoryModalOpen,
    status, stores, projectFilter, projectFilterOptions, knowledgeTargets, currentTargetId, currentStore, managedContext,
    files, filesLoading,
    messages, setMessages,
    loading,
    sessionId, setSessionId,
    theme, toggleTheme,
    toggleSidebar, showStatus,
    refreshStores, handleRefreshKnowledge, setProjectFilter,
    handleStoreChange, handleRestartChat,
    handleCreateStore, handleDeleteStore,
    handleUploadFile, handleDeleteFile,
    handleSendMessage, handleRegenerate, handleEditAndResend,
  } = useAppChat();

  return (
    <>
      <div className="app-container">
        <Header
          status={status}
          onToggleSidebar={toggleSidebar}
          sidebarOpen={sidebarOpen}
          onOpenStoreManagement={() => setStoreModalOpen(true)}
          onOpenUserApiKeySettings={() => setUserApiKeyModalOpen(true)}
          activeGeminiKeyName={activeGeminiKeyName === 'system' ? '系統預設' : activeGeminiKeyName}
          onOpenConversationHistory={() => setConversationHistoryModalOpen(true)}
          onRestartChat={handleRestartChat}
          canOpenConversationHistory={Boolean(currentStore)}
          canRestartChat={Boolean(currentStore)}
          theme={theme}
          onToggleTheme={toggleTheme}
        />
        <div className="app-content">
          <Sidebar
            isOpen={sidebarOpen}
            projectFilter={projectFilter}
            projectFilterOptions={projectFilterOptions}
            knowledgeTargets={knowledgeTargets}
            currentTargetId={currentTargetId}
            managedContext={managedContext}
            files={files}
            filesLoading={filesLoading}
            onProjectFilterChange={setProjectFilter}
            onTargetChange={handleStoreChange}
            onUploadFile={handleUploadFile}
            onDeleteFile={handleDeleteFile}
            onRefresh={handleRefreshKnowledge}
            onOpenPromptManagement={() => setPromptModalOpen(true)}
            onShowStatus={showStatus}
          />
          <ChatArea
            messages={messages}
            onSendMessage={handleSendMessage}
            disabled={!currentStore}
            loading={loading}
            onRegenerate={handleRegenerate}
            onEditAndResend={handleEditAndResend}
          />
        </div>
      </div>
      <StoreManagementModal
        isOpen={storeModalOpen}
        onClose={() => setStoreModalOpen(false)}
        stores={stores}
        currentStore={currentStore}
        onCreateStore={handleCreateStore}
        onDeleteStore={handleDeleteStore}
        onRefresh={refreshStores}
      />
      <PromptManagementModal
        isOpen={promptModalOpen}
        onClose={() => setPromptModalOpen(false)}
        currentStore={currentStore}
        onRestartChat={handleRestartChat}
        stores={stores}
      />
      <UserApiKeyModal
        isOpen={userApiKeyModalOpen}
        onClose={() => setUserApiKeyModalOpen(false)}
        onApiKeySaved={() => {
          showStatus('✅ API Key 已儲存');
          void handleRefreshKnowledge();
        }}
      />
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
