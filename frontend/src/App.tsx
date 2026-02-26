import Header from './components/Header';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import StoreManagementModal from './components/StoreManagementModal';
import PromptManagementModal from './components/PromptManagementModal';
import UserApiKeyModal from './components/UserApiKeyModal';
import ConversationHistoryModal from './components/ConversationHistoryModal';
import Jti from './pages/Jti';
import { useAppChat } from './hooks/useAppChat';
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

  const page = window.location.pathname.replace(/^\//, '').toLowerCase() || 'home';

  const isJtiPage =
    (page === 'jti' && canShow('jti')) ||
    (!canShow('home') && canShow('jti'));

  if (isJtiPage) {
    if (page !== 'jti') window.history.replaceState(null, '', '/jti');
    return <Jti />;
  }

  const {
    sidebarOpen,
    storeModalOpen, setStoreModalOpen,
    promptModalOpen, setPromptModalOpen,
    userApiKeyModalOpen, setUserApiKeyModalOpen,
    conversationHistoryModalOpen, setConversationHistoryModalOpen,
    status, stores, currentStore,
    files, filesLoading,
    messages, setMessages,
    loading,
    sessionId, setSessionId,
    theme, toggleTheme,
    toggleSidebar, showStatus,
    refreshStores, refreshFiles,
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
          onOpenConversationHistory={() => setConversationHistoryModalOpen(true)}
          onRestartChat={handleRestartChat}
          theme={theme}
          onToggleTheme={toggleTheme}
        />
        <div className="app-content">
          <Sidebar
            isOpen={sidebarOpen}
            stores={stores}
            currentStore={currentStore}
            files={files}
            filesLoading={filesLoading}
            onStoreChange={handleStoreChange}
            onUploadFile={handleUploadFile}
            onDeleteFile={handleDeleteFile}
            onRefresh={refreshStores}
            onOpenPromptManagement={() => setPromptModalOpen(true)}
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
          refreshStores();
          refreshFiles();
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
          })));
          // General 模式目前不處理語言切換（沒有多語言支援）
        }}
      />
    </>
  );
}
