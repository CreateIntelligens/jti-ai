import { useEffect, useState, type ComponentType, type ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { AlertTriangle, LogOut } from 'lucide-react';
import { hasKnownAuthSession, logout } from './services/api';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import AdminPanel from './components/AdminPanel';
import ApiKeysPanel from './components/ApiKeysPanel';
import PromptPanel from './components/PromptPanel';
import ExtKeysPanel from './components/ExtKeysPanel';
import UsersPanel from './components/UsersPanel';
import ConversationHistoryModal from './components/ConversationHistoryModal';
import GeneralKnowledgeWorkspace from './components/general/GeneralKnowledgeWorkspace';
import HciotKnowledgeWorkspace from './components/hciot/HciotKnowledgeWorkspace';
import JtiKnowledgeWorkspace from './components/jti/JtiKnowledgeWorkspace';
import EsgKnowledgeWorkspace from './components/esg/EsgKnowledgeWorkspace';
import Jti from './pages/Jti';
import Hciot from './pages/Hciot';
import General from './pages/General';
import Login from './pages/Login';
import { useAppChat } from './hooks/useAppChat';
import { useCurrentUserProfile } from './hooks/useCurrentUserProfile';
import { PROJECT_COLORS, getStoreIcon } from './utils/storeDisplay';
import { getProfileRedirectPath, isAdminRole, isGeneralUserScope } from './utils/authRouting';
import type { AppTarget, KnowledgeLanguage } from './types';
import './styles/shared/index.css';
import './styles/shared/animations.css';
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
import './styles/conversation-history-detail.css';
import './styles/conversation-history-light.css';

type PanelId = 'admin' | 'apikeys' | 'prompt' | 'extkeys' | 'users' | null;

// 固定庫（hciot/jti/esg）的文件工作區都吃相同 props；以 appTarget 為 key 查表
// 渲染，新增 app 只要在此註冊一行，不必再加一段 if/三元。其餘（general）走
// 預設的 GeneralKnowledgeWorkspace（吃 storeName 而非 language）。
type FixedAppWorkspaceComponent = ComponentType<{
  active: boolean;
  language: KnowledgeLanguage;
  onTopicsChanged?: () => Promise<void> | void;
}>;

const FIXED_APP_WORKSPACES: Partial<Record<AppTarget, FixedAppWorkspaceComponent>> = {
  hciot: HciotKnowledgeWorkspace,
  jti: JtiKnowledgeWorkspace,
  esg: EsgKnowledgeWorkspace,
};

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
  const { profile, loading, error } = useCurrentUserProfile({
    enabled: hasKnownAuthSession(),
  });
  const location = useLocation();
  const navigate = useNavigate();

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
        <div className="auth-guard-error-page">
          <div className="auth-guard-error-card">
            <div className="auth-guard-error-icon">
              <AlertTriangle size={32} />
            </div>
            <h1 className="auth-guard-error-title">無存取權限</h1>
            <p className="auth-guard-error-message">
              此主機或服務不包含「<strong>{targetPage}</strong>」頁面。<br />
              請聯絡系統開發人員取得協助。
            </p>
            <button
              className="auth-guard-error-btn"
              onClick={async () => {
                await logout().catch(() => {});
                navigate('/login', { replace: true });
              }}
            >
              <LogOut size={14} />
              <span>返回登入頁</span>
            </button>
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

  const allowedPages = (import.meta.env.VITE_PUBLIC_ALLOWED_PAGES || 'home,hciot,jti,esg')
    .split(',').map((s: string) => s.trim().toLowerCase()).filter(Boolean);
  const canShow = (p: string) => !isRestricted || allowedPages.includes(p) || (p === 'home' && allowedPages.includes('esg'));
  const fallback = isRestricted
    ? (allowedPages[0] === 'home' || !allowedPages[0] ? '/' : `/${allowedPages[0]}`)
    : '/';

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
                <HomeShell canShow={canShow} />
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

function HomeShell({ canShow }: { canShow: (page: string) => boolean }) {
  const { profile, setProfile } = useCurrentUserProfile();
  const isAdmin = isAdminRole(profile?.role);
  useEffect(() => {
    if (localStorage.getItem('theme') === null) {
      localStorage.setItem('theme', 'light');
    }
  }, []);

  const {
    sidebarOpen,
    conversationHistoryModalOpen, setConversationHistoryModalOpen,
    status, stores, filteredStores, keyNames,
    knowledgeTargets, currentTarget, currentTargetId, currentStore,
    messages, setMessages,
    loading,
    initializing,
    sessionId, setSessionId,
    managedContext,
    theme, toggleTheme,
    toggleSidebar, showStatus,
    refreshStores, handleRefreshKnowledge,
    handleStoreChange, handleRestartChat,
    handleCreateStore, handleDeleteStore,
    handleSendMessage, handleRegenerate, handleEditAndResend,
  } = useAppChat(isAdmin);

  const [panel, setPanel] = useState<PanelId>(null);
  const openPanel = (id: PanelId) => setPanel(id);
  const closePanel = () => setPanel(null);

  const [knowledgeWorkspaceView, setKnowledgeWorkspaceView] = useState<'chat' | 'files'>('chat');

  // 切換知識庫或失去 admin/store 時，自動退回對話檢視，並確保側邊欄展開。
  useEffect(() => {
    setKnowledgeWorkspaceView('chat');
    if (!sidebarOpen) {
      toggleSidebar();
    }
  }, [currentStore]);

  // Derive store display info for chat area
  const activeStore = currentTarget?.kind === 'store'
    ? stores.find((s) => s.name === currentTarget.storeName)
    : null;
  const currentStoreName = activeStore ? (activeStore.display_name || activeStore.name) : null;
  const currentStoreIcon = getStoreIcon(activeStore?.managed_app || '');
  const currentProjectIdx = typeof activeStore?.key_index === 'number' ? activeStore.key_index : 0;
  const currentProjectName = keyNames[currentProjectIdx]
    || (keyNames.length > 0 ? `Key #${currentProjectIdx + 1}` : '全部專案');
  const currentProjectColor = PROJECT_COLORS[currentProjectIdx % PROJECT_COLORS.length];

  return (
    <div className="app-container">
      <div className={`app-shell ${sidebarOpen ? 'sidebar-open' : 'sidebar-closed'}`}>
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
          onOpenPromptPanel={() => openPanel('prompt')}
          onRefresh={handleRefreshKnowledge}
          onShowStatus={showStatus}
          userProfile={profile}
          canShow={canShow}
          onOpenUsersPanel={() => openPanel('users')}
          onLogout={() => setProfile(null)}
        />
        <div className="app-body">
          {knowledgeWorkspaceView === 'chat' && (
            <Sidebar
              isOpen={sidebarOpen}
              stores={filteredStores}
              keyNames={keyNames}
              knowledgeTargets={knowledgeTargets}
              currentTargetId={currentTargetId}
              onTargetChange={handleStoreChange}
              onCreateStore={handleCreateStore}
              canManageKnowledge={isAdmin}
            />
          )}
          <General
            storeName={currentStore}
            appTarget={managedContext?.appTarget}
            appLanguage={managedContext?.language}
            messages={messages}
            onSendMessage={handleSendMessage}
            disabled={!currentStore || initializing}
            loading={loading}
            onRegenerate={handleRegenerate}
            onEditAndResend={handleEditAndResend}
            currentStoreName={currentStoreName}
            currentStoreIcon={currentStoreIcon}
            currentProjectName={currentProjectName}
            currentProjectColor={currentProjectColor}
            onOpenPromptPanel={() => openPanel('prompt')}
            onRestartChat={handleRestartChat}
            onCreateStore={isAdmin ? () => openPanel('admin') : undefined}
            viewMode={knowledgeWorkspaceView}
            onChangeView={setKnowledgeWorkspaceView}
            /* 設計稿：只要選了知識庫就顯示「對話/文件」toggle，
               不再限制 admin / 非 managed。 */
            filesViewEnabled={Boolean(currentStore)}
            filesView={
              currentStore ? (() => {
                const onTopicsChanged = () => { void handleRefreshKnowledge(); };
                const active = knowledgeWorkspaceView === 'files';
                // 固定庫（hciot/jti/esg）的檔案歸各自 app 的 admin API，不走
                // general API（否則列表會是空的）；以 appTarget 查表渲染。
                const FixedWorkspace = managedContext
                  ? FIXED_APP_WORKSPACES[managedContext.appTarget]
                  : undefined;
                return FixedWorkspace && managedContext ? (
                  <FixedWorkspace
                    active={active}
                    language={managedContext.language}
                    onTopicsChanged={onTopicsChanged}
                  />
                ) : (
                  <GeneralKnowledgeWorkspace
                    active={active}
                    storeName={currentStore}
                    onTopicsChanged={onTopicsChanged}
                  />
                );
              })() : undefined
            }
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
        stores={stores}
        isAdmin={isAdmin}
        onShowStatus={showStatus}
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
        isAdmin={isAdmin}
        onApiKeySaved={() => {
          showStatus('✅ API Key 已儲存');
          void handleRefreshKnowledge();
        }}
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
