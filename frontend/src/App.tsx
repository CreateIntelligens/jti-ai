import { useState, type ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import AdminPanel from './components/AdminPanel';
import ApiKeysPanel from './components/ApiKeysPanel';
import PromptPanel from './components/PromptPanel';
import ExtKeysPanel from './components/ExtKeysPanel';
import UsersPanel from './components/UsersPanel';
import ConversationHistoryModal from './components/ConversationHistoryModal';
import FilePreviewModal from './components/FilePreviewModal';
import Jti from './pages/Jti';
import Hciot from './pages/Hciot';
import Login from './pages/Login';
import { useAppChat } from './hooks/useAppChat';
import { useCurrentUserProfile } from './hooks/useCurrentUserProfile';
import { PROJECT_COLORS, getStoreIcon } from './utils/storeDisplay';
import { getProfileRedirectPath, isAdminRole, isGeneralUserScope } from './utils/authRouting';
import type { FileItem } from './types';
import './styles/shared/index.css';
import './styles/app/layout.css';
import './styles/app/forms.css';
import './styles/app/components.css';
import './styles/app/messages.css';
import './styles/app/light.css';
import './styles/app/variables.css';
import './styles/app/shell.css';
import './styles/app/panel.css';
import './styles/app/buttons.css';
import './styles/app/utility.css';
import './styles/conversation-history.css';

type PanelId = 'admin' | 'apikeys' | 'prompt' | 'extkeys' | 'users' | null;

interface AuthGuardProps {
  children: ReactNode;
  allowedRoles?: string[];
  allowedApp?: string;
  allowGeneralUser?: boolean;
  // 回報某頁是否在當前主機/環境開放（由 App 的 canShow 注入）
  canShow?: (page: string) => boolean;
}

// 把 redirect 目標路徑對應回「頁名」，用於提示訊息
function pageNameForPath(path: string): string {
  switch (path) {
    case '/': return 'home';
    case '/jti': return 'jti';
    case '/hciot': return 'hciot';
    default: return path;
  }
}

function AuthGuard({ children, allowedRoles, allowedApp, allowGeneralUser = false, canShow }: AuthGuardProps) {
  const { profile, loading, error } = useCurrentUserProfile();
  const location = useLocation();

  if (loading) {
    return (
      <div className="auth-guard-loading-container">
        <div className="auth-guard-spinner" />
        <div className="auth-guard-text">Loading profile...</div>
      </div>
    );
  }

  if (error || !profile) {
    return <Navigate to="/login" replace />;
  }

  const roleBlocked =
    allowedRoles
    && !allowedRoles.includes(profile.role)
    && !(allowGeneralUser && isGeneralUserScope(profile));
  const isSimpleUser = profile.role !== 'admin' && profile.role !== 'super_admin';
  const appBlocked = Boolean(allowedApp && isSimpleUser && profile.scope !== allowedApp);

  if (roleBlocked || appBlocked) {
    const target = getProfileRedirectPath(profile);
    const targetPage = pageNameForPath(target);
    // 目標頁在此環境不開放，或目標就是當前頁（會造成 redirect loop）→
    // 不再 Navigate，直接顯示明確提示，避免空白或瘋狂重整。
    const targetUnavailable = canShow ? !canShow(targetPage) : false;
    if (target === location.pathname || targetUnavailable) {
      return (
        <div className="auth-guard-loading-container">
          <div className="auth-guard-text">
            此主機或服務不包含「{targetPage}」頁面，請聯絡開發人員。
          </div>
        </div>
      );
    }
    return <Navigate to={target} replace />;
  }

  return <>{children}</>;
}

export default function App() {
  // 受限 hostname（外網 domain）只顯示 ALLOWED_PAGES；其餘顯示全部
  const restrictedHosts = (import.meta.env.VITE_PUBLIC_RESTRICTED_HOSTS || '')
    .split(',').map((s: string) => s.trim().toLowerCase()).filter(Boolean);
  const isRestricted = restrictedHosts.includes(window.location.hostname.toLowerCase());

  const allowedPages = (import.meta.env.VITE_PUBLIC_ALLOWED_PAGES || 'jti')
    .split(',').map((s: string) => s.trim().toLowerCase()).filter(Boolean);
  const canShow = (p: string) => !isRestricted || allowedPages.includes(p);
  const fallback = isRestricted ? `/${allowedPages[0] || 'jti'}` : '/';

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/jti"
          element={
            canShow('jti') ? (
              <AuthGuard allowedApp="jti" canShow={canShow}>
                <Jti />
              </AuthGuard>
            ) : (
              <Navigate to={fallback} replace />
            )
          }
        />
        <Route
          path="/hciot"
          element={
            canShow('hciot') ? (
              <AuthGuard allowedApp="hciot" canShow={canShow}>
                <Hciot />
              </AuthGuard>
            ) : (
              <Navigate to={fallback} replace />
            )
          }
        />
        <Route
          path="/"
          element={
            canShow('home') ? (
              <AuthGuard allowedRoles={['admin', 'super_admin']} allowGeneralUser canShow={canShow}>
                <HomeShell />
              </AuthGuard>
            ) : (
              <Navigate to={fallback} replace />
            )
          }
        />
        <Route path="*" element={<Navigate to={fallback} replace />} />
      </Routes>
    </BrowserRouter>
  );
}

function HomeShell() {
  const { profile, setProfile } = useCurrentUserProfile();
  const isAdmin = isAdminRole(profile?.role);

  const {
    sidebarOpen,
    conversationHistoryModalOpen, setConversationHistoryModalOpen,
    status, stores, filteredStores, keyNames,
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
  } = useAppChat(isAdmin);

  const [panel, setPanel] = useState<PanelId>(null);
  const openPanel = (id: PanelId) => setPanel(id);
  const closePanel = () => setPanel(null);

  const [previewFile, setPreviewFile] = useState<FileItem | null>(null);

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
    <div className="app-container">
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
          onOpenExtKeysPanel={() => openPanel('extkeys')}
          onShowStatus={showStatus}
          userProfile={profile}
          onOpenUsersPanel={() => openPanel('users')}
          onLogout={() => setProfile(null)}
        />
        <div className="app-body">
          <Sidebar
            isOpen={sidebarOpen}
            stores={filteredStores}
            keyNames={keyNames}
            knowledgeTargets={knowledgeTargets}
            currentTargetId={currentTargetId}
            files={files}
            filesLoading={filesLoading}
            onTargetChange={handleStoreChange}
            onUploadFile={handleUploadFile}
            onDeleteFile={handleDeleteFile}
            onCreateStore={handleCreateStore}
            onOpenFile={(f) => setPreviewFile(f)}
            canManageKnowledge={isAdmin}
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
            onOpenPromptPanel={isAdmin ? () => openPanel('prompt') : undefined}
            onRestartChat={handleRestartChat}
            onCreateStore={isAdmin ? () => openPanel('admin') : undefined}
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
      <UsersPanel
        isOpen={panel === 'users'}
        onClose={closePanel}
        currentUserRole={profile?.role}
        currentUserId={profile?.user_id}
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
        isAdmin={isAdmin}
        onShowStatus={showStatus}
      />

      <FilePreviewModal
        isOpen={previewFile !== null}
        store={activeStore || null}
        file={previewFile}
        onClose={() => setPreviewFile(null)}
        onSaved={() => { void handleRefreshKnowledge(); }}
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
    </div>
  );
}
