# JTAI RBAC & Auth Frontend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the frontend authentication layer, the login page, redirection based on role and app, logout controls, route guards, a backend users management panel (UsersPanel), and disable same-origin automatic admin access in the backend auth middleware.

**Architecture:** 
1. Backend `verify_auth` is updated to check for the HTTP-only `session` cookie and remove same-origin default admin authorization.
2. A new `GET /api/auth/me` endpoint returns current user info.
3. The frontend `App` handles routing, routing checks, and route guards.
4. A modern, premium glassmorphism `/login` page is created.
5. A slide-out `UsersPanel` is added to `/general` for CRUD operations on accounts.

**Tech Stack:** React 19, TypeScript, React Router 7, Vite, Lucide React, FastAPI, PyJWT, MongoDB

---

### Task 1: Backend Auth Cookie and Me API

**Files:**
- Modify: `app/auth.py`
- Modify: `app/routers/auth_routes.py`
- Modify: `tests/test_auth.py`
- Modify: `tests/auth/test_require_role.py`

**Step 1: Write backend tests for cookie auth and /me API**

Create a test for extracting the token from the cookie, and for the `/api/auth/me` endpoint in `tests/auth/test_require_role.py`.
Modify same-origin tests in `tests/test_auth.py` and `tests/auth/test_require_role.py` to expect a 401 error.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_auth.py tests/auth/test_require_role.py -v`
Expected: FAIL (missing cookie extraction, `me` endpoint not defined, same-origin tests fail to raise 401)

**Step 3: Implement backend cookie extraction and /me endpoint**

1. Modify `app/auth.py:157-163` to extract the session token from cookies when headers are empty, and remove same-origin automatic authorization:
```python
    # 提取 token（支援 Authorization: Bearer 與 API-Token，以及 Cookie: session）
    token = _extract_bearer_token(request) or _extract_api_token(request)
    if not token:
        token = request.cookies.get("session")
    
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization credentials")
```
2. Add `GET /api/auth/me` to `app/routers/auth_routes.py`:
```python
@router.get("/me")
def get_me(auth: dict = Depends(deps.verify_auth)):
    """獲取當前登入使用者的資訊。"""
    username = None
    if auth.get("user_id") and deps.user_manager:
        user = deps.user_manager.get_user(auth["user_id"])
        if user:
            username = user.username
    return {
        "user_id": auth.get("user_id"),
        "username": username,
        "role": auth.get("role"),
        "app": auth.get("app"),
        "store_name": auth.get("store_name"),
    }
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_auth.py tests/auth/test_require_role.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/auth.py app/routers/auth_routes.py tests/test_auth.py tests/auth/test_require_role.py
git commit -m "backend: add cookie auth, /api/auth/me, and remove same-origin safety hole"
```

---

### Task 2: Frontend Auth Service

**Files:**
- Modify: `frontend/src/services/api/base.ts`
- Create: `frontend/src/services/api/auth.ts`
- Modify: `frontend/src/services/api/index.ts`

**Step 1: Write tests for frontend auth service**

We will write unit tests for the frontend API methods if needed, or simply verify the type declarations and builds.

**Step 2: Implement frontend auth requests**

1. Create `frontend/src/services/api/auth.ts` to map `/api/auth/login`, `/api/auth/logout`, `/api/auth/me`, and account CRUD operations:
```typescript
import { API_BASE, handleResponse } from './base';

export interface UserProfile {
  user_id: string | null;
  username: string | null;
  role: string;
  app: string | null;
  store_name: string | null;
}

export interface UserAccount {
  id: string;
  username: string;
  role: string;
  app: string | null;
  store_name: string | null;
  disabled: boolean;
  created_by?: string | null;
  created_at: string;
}

export async function login(username: string, password: string): Promise<{ token: string; role: string; app: string | null }> {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  return handleResponse(response);
}

export async function logout(): Promise<{ ok: boolean }> {
  const response = await fetch(`${API_BASE}/auth/logout`, { method: 'POST' });
  return handleResponse(response);
}

export async function getMe(): Promise<UserProfile> {
  const response = await fetch(`${API_BASE}/auth/me`);
  return handleResponse<UserProfile>(response);
}

export async function listUsers(): Promise<UserAccount[]> {
  const response = await fetch(`${API_BASE}/users`);
  return handleResponse<UserAccount[]>(response);
}

export async function createUser(data: {
  username: string;
  password: string;
  role: string;
  app?: string | null;
  store_name?: string | null;
}): Promise<UserAccount> {
  const response = await fetch(`${API_BASE}/users`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse<UserAccount>(response);
}

export async function setUserDisabled(userId: string, disabled: boolean): Promise<UserAccount> {
  const response = await fetch(`${API_BASE}/users/${userId}/disabled`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ disabled }),
  });
  return handleResponse<UserAccount>(response);
}

export async function deleteUser(userId: string): Promise<{ message: string }> {
  const response = await fetch(`${API_BASE}/users/${userId}`, { method: 'DELETE' });
  return handleResponse(response);
}
```
2. Update `frontend/src/services/api/index.ts` to export everything from `auth.ts`.
3. In `frontend/src/services/api/base.ts`, replace `fetchAsAdmin` to use standard fetch since cookies will automatically be attached by the browser:
```typescript
export async function fetchAsAdmin(url: string, options: RequestInit = {}): Promise<Response> {
  return fetch(url, options);
}
```

**Step 3: Run build to verify TypeScript compiles**

Run: `pnpm build`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/services/api/base.ts frontend/src/services/api/auth.ts frontend/src/services/api/index.ts
git commit -m "frontend: add auth API service functions"
```

---

### Task 3: Premium Redesigned Login Page

**Files:**
- Create: `frontend/src/pages/Login.tsx`
- Create: `frontend/src/styles/app/login.css`

**Step 1: Create Login styling using relative units and a sleek space/glassmorphism design**

Create `frontend/src/styles/app/login.css`:
```css
.login-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100dvh;
  width: 100%;
  background: radial-gradient(circle at 10% 20%, rgba(20, 24, 42, 1) 0%, rgba(12, 14, 26, 1) 100%);
  font-family: 'Inter', sans-serif;
  color: var(--hciot-text, #f8fafc);
  padding: 1.5rem;
}

.login-card {
  width: 100%;
  max-width: 26rem;
  background: rgba(25, 30, 52, 0.65);
  backdrop-filter: blur(0.75rem);
  -webkit-backdrop-filter: blur(0.75rem);
  border: 0.0625rem solid rgba(255, 255, 255, 0.08);
  border-radius: 1rem;
  padding: 2.5rem 2rem;
  box-shadow: 0 2rem 3.5rem rgba(0, 0, 0, 0.5);
  display: flex;
  flex-direction: column;
  gap: 1.75rem;
}

.login-header {
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.login-logo {
  font-size: 2.25rem;
  font-weight: 800;
  letter-spacing: -0.0625rem;
  background: linear-gradient(135deg, #a5b4fc 0%, #6366f1 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.login-subtitle {
  color: #94a3b8;
  font-size: 0.875rem;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.login-input-group {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.login-input-label {
  font-size: 0.8rem;
  font-weight: 500;
  color: #cbd5e1;
}

.login-input {
  width: 100%;
  padding: 0.75rem 1rem;
  background: rgba(15, 23, 42, 0.6);
  border: 0.0625rem solid rgba(255, 255, 255, 0.1);
  border-radius: 0.5rem;
  color: white;
  font-size: 0.875rem;
  transition: all 0.2s ease;
}

.login-input:focus {
  outline: none;
  border-color: #6366f1;
  box-shadow: 0 0 0 0.1875rem rgba(99, 102, 241, 0.2);
}

.login-button {
  width: 100%;
  padding: 0.75rem;
  background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
  border: none;
  border-radius: 0.5rem;
  color: white;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}

.login-button:hover:not(:disabled) {
  background: linear-gradient(135deg, #818cf8 0%, #6366f1 100%);
  transform: translateY(-0.0625rem);
}

.login-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.login-error {
  background: rgba(239, 68, 68, 0.1);
  border: 0.0625rem solid rgba(239, 68, 68, 0.2);
  color: #fca5a5;
  padding: 0.625rem;
  border-radius: 0.375rem;
  font-size: 0.8rem;
  text-align: center;
}
```

**Step 2: Create Login Component**

Implement `frontend/src/pages/Login.tsx`:
```tsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as api from '../services/api';
import '../styles/app/login.css';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) return;

    setError(null);
    setLoading(true);

    try {
      const res = await api.login(username.trim(), password);
      if (res.role === 'user') {
        if (res.app === 'hciot') navigate('/hciot');
        else if (res.app === 'jti') navigate('/jti');
        else navigate('/'); // Fallback
      } else {
        navigate('/'); // admin / super_admin go to general
      }
    } catch (err: any) {
      setError(err.message || '登入失敗，請檢查帳號密碼。');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-header">
          <span className="login-logo">JTAI Portal</span>
          <span className="login-subtitle">請輸入您的帳號密碼以登入系統</span>
        </div>

        <form className="login-form" onSubmit={handleLogin}>
          {error && <div className="login-error">{error}</div>}

          <div className="login-input-group">
            <label className="login-input-label">使用者名稱</label>
            <input
              type="text"
              className="login-input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Username"
              disabled={loading}
              required
            />
          </div>

          <div className="login-input-group">
            <label className="login-input-label">密碼</label>
            <input
              type="password"
              className="login-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              disabled={loading}
              required
            />
          </div>

          <button type="submit" className="login-button" disabled={loading}>
            {loading ? '登入中...' : '登入'}
          </button>
        </form>
      </div>
    </div>
  );
}
```

**Step 3: Run build to verify TypeScript compiles**

Run: `pnpm build`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/pages/Login.tsx frontend/src/styles/app/login.css
git commit -m "frontend: add premium redesigned login page"
```

---

### Task 4: Routes Guarding and Setup

**Files:**
- Modify: `frontend/src/App.tsx`

**Step 1: Modify Routing logic to support Auth checking & protection**

1. Set up an authentication context/state checks. On mount, fetch `/api/auth/me`.
2. Add route guards:
   - For `/general` (which is `/` root shell), redirect to `/login` if not logged in. Redirect to user's assigned app if the role is `"user"`.
   - For `/hciot`, redirect to `/login` if not logged in. If role is `"user"` but `app !== "hciot"`, redirect to `/jti`.
   - For `/jti`, redirect to `/login` if not logged in. If role is `"user"` but `app !== "jti"`, redirect to `/hciot`.
   - For `/login`, if already logged in, redirect based on role and app.

Let's modify `frontend/src/App.tsx`:
```tsx
import { useEffect, useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import AdminPanel from './components/AdminPanel';
import ApiKeysPanel from './components/ApiKeysPanel';
import PromptPanel from './components/PromptPanel';
import ExtKeysPanel from './components/ExtKeysPanel';
import UsersPanel from './components/UsersPanel'; // Will be created in Task 5
import ConversationHistoryModal from './components/ConversationHistoryModal';
import FilePreviewModal from './components/FilePreviewModal';
import Jti from './pages/Jti';
import Hciot from './pages/Hciot';
import Login from './pages/Login';
import * as api from './services/api';
import { useAppChat } from './hooks/useAppChat';
import { PROJECT_COLORS, getStoreIcon } from './utils/storeDisplay';
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
  children: React.ReactNode;
  allowedRoles?: string[];
  allowedApp?: 'hciot' | 'jti' | null;
}

function AuthGuard({ children, allowedRoles, allowedApp }: AuthGuardProps) {
  const [profile, setProfile] = useState<api.UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    api.getMe()
      .then((p) => {
        if (active) {
          setProfile(p);
          setLoading(false);
        }
      })
      .catch(() => {
        if (active) {
          setLoading(false);
          navigate('/login', { replace: true });
        }
      });
    return () => { active = false; };
  }, [navigate]);

  if (loading) {
    return <div className="app-loading-screen" style={{ color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100dvh', background: '#0b0c16' }}>驗證身分中...</div>;
  }

  if (!profile) return null;

  if (allowedRoles && !allowedRoles.includes(profile.role)) {
    // Insufficient permissions. User is a simple 'user' trying to access /general
    if (profile.role === 'user') {
      const target = profile.app === 'hciot' ? '/hciot' : '/jti';
      return <Navigate to={target} replace />;
    }
    return <Navigate to="/" replace />;
  }

  if (profile.role === 'user' && allowedApp && profile.app !== allowedApp) {
    const target = profile.app === 'hciot' ? '/hciot' : '/jti';
    return <Navigate to={target} replace />;
  }

  return <>{children}</>;
}

export default function App() {
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
              <AuthGuard allowedApp="jti">
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
              <AuthGuard allowedApp="hciot">
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
              <AuthGuard allowedRoles={['admin', 'super_admin']}>
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
```

**Step 2: Run build to verify TypeScript compiles**

Run: `pnpm build`
Expected: PASS (will fail if UsersPanel isn't created yet, so let's stub `UsersPanel.tsx` with a basic component first)

**Step 3: Create stub `UsersPanel.tsx`**

Create `frontend/src/components/UsersPanel.tsx`:
```tsx
interface UsersPanelProps {
  isOpen: boolean;
  onClose: () => void;
  currentUserRole?: string;
  currentUserId?: string | null;
}

export default function UsersPanel({ isOpen, onClose }: UsersPanelProps) {
  if (!isOpen) return null;
  return (
    <div className="rp-overlay" onClick={onClose}>
      <div className="rp-panel" onClick={(e) => e.stopPropagation()}>
        <div>帳號管理後台 (開發中)</div>
        <button onClick={onClose}>關閉</button>
      </div>
    </div>
  );
}
```

**Step 4: Run build**

Run: `pnpm build`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/UsersPanel.tsx
git commit -m "frontend: set up auth guards, redirection routes, and routing structure"
```

---

### Task 5: Users Panel Implementation (UsersPanel)

**Files:**
- Modify: `frontend/src/components/UsersPanel.tsx`
- Modify: `frontend/src/App.tsx` (wire up current user's profile role to panel if needed)

**Step 1: Implement full CRUD in UsersPanel**

Modify `frontend/src/components/UsersPanel.tsx` to call `/api/users` endpoints:
- List accounts with details.
- Show "Add Account" form (Username, password, role, app, store_name).
- Check caller's role (admin can only list/create role "user", app dropdown only visible for role="user").
- Toggle enabled/disabled (`PATCH /api/users/{user_id}/disabled`).
- Delete account (`DELETE /api/users/{user_id}`).
- Prevent modifying super_admin by other admins.

```tsx
import { useState, useEffect } from 'react';
import { X, UserPlus, Power, Trash2 } from 'lucide-react';
import * as api from '../services/api';
import { useEscapeKey } from '../hooks/useEscapeKey';

interface UsersPanelProps {
  isOpen: boolean;
  onClose: () => void;
  currentUserRole?: string;
  currentUserId?: string | null;
}

export default function UsersPanel({ isOpen, onClose, currentUserRole = 'admin', currentUserId }: UsersPanelProps) {
  const [users, setUsers] = useState<api.UserAccount[]>([]);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('user');
  const [app, setApp] = useState('hciot');
  const [storeName, setStoreName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEscapeKey(onClose, isOpen);

  const loadUsers = async () => {
    try {
      const data = await api.listUsers();
      setUsers(data);
    } catch (err: any) {
      console.error(err);
    }
  };

  useEffect(() => {
    if (isOpen) {
      void loadUsers();
      setUsername('');
      setPassword('');
      setRole('user');
      setApp('hciot');
      setStoreName('');
      setError(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) return;

    setLoading(true);
    setError(null);

    const payload = {
      username: username.trim(),
      password,
      role,
      app: role === 'user' ? app : null,
      store_name: role === 'user' && storeName.trim() ? storeName.trim() : null,
    };

    try {
      await api.createUser(payload);
      setUsername('');
      setPassword('');
      setStoreName('');
      void loadUsers();
    } catch (err: any) {
      setError(err.message || '建立帳號失敗');
    } finally {
      setLoading(false);
    }
  };

  const handleToggleDisabled = async (userId: string, currentStatus: boolean) => {
    try {
      await api.setUserDisabled(userId, !currentStatus);
      void loadUsers();
    } catch (err: any) {
      alert(err.message || '切換狀態失敗');
    }
  };

  const handleDelete = async (userId: string, name: string) => {
    if (!confirm(`確定要刪除「${name}」帳號嗎？`)) return;
    try {
      await api.deleteUser(userId);
      void loadUsers();
    } catch (err: any) {
      alert(err.message || '刪除失敗');
    }
  };

  return (
    <div className="rp-overlay" onClick={onClose}>
      <div className="rp-panel" onClick={(e) => e.stopPropagation()}>
        <div className="rp-header">
          <span className="rp-title">帳號管理</span>
          <button className="icon-btn" onClick={onClose}><X size={18} /></button>
        </div>

        <div className="rp-body" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Create User Form */}
          <div>
            <div className="rp-section-title">新增帳號</div>
            <form onSubmit={handleCreate} className="rp-form-stack" style={{ gap: '0.75rem' }}>
              {error && <div className="login-error" style={{ fontSize: '0.75rem', padding: '0.4rem' }}>{error}</div>}
              
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <input
                  className="input-base"
                  style={{ flex: 1 }}
                  placeholder="使用者名稱"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                />
                <input
                  className="input-base"
                  style={{ flex: 1 }}
                  type="password"
                  placeholder="密碼"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>

              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                <select
                  className="input-base"
                  style={{ flex: 1 }}
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                >
                  <option value="user">一般用戶 (user)</option>
                  {currentUserRole === 'super_admin' && (
                    <>
                      <option value="admin">管理者 (admin)</option>
                      <option value="super_admin">超級管理員 (super_admin)</option>
                    </>
                  )}
                </select>

                {role === 'user' && (
                  <select
                    className="input-base"
                    style={{ flex: 1 }}
                    value={app}
                    onChange={(e) => setApp(e.target.value)}
                  >
                    <option value="hciot">hciot</option>
                    <option value="jti">jti</option>
                  </select>
                )}
              </div>

              {role === 'user' && (
                <input
                  className="input-base"
                  placeholder="綁定 Store 名稱 (非必填)"
                  value={storeName}
                  onChange={(e) => setStoreName(e.target.value)}
                />
              )}

              <button type="submit" className="btn btn-primary btn-sm" style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }} disabled={loading}>
                <UserPlus size={14} />
                {loading ? '建立中...' : '建立'}
              </button>
            </form>
          </div>

          <div className="sep-row"><div className="sep-line" /></div>

          {/* User List */}
          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <div className="rp-section-title">帳號列表</div>
            <div className="rp-stack">
              {users.map((u) => {
                const isSelf = u.id === currentUserId;
                const canModify = currentUserRole === 'super_admin' ? !isSelf : u.role === 'user';

                return (
                  <div key={u.id} className="key-card" style={{ opacity: u.disabled ? 0.6 : 1 }}>
                    <div className="kc-info">
                      <div className="kc-name-row">
                        <span className="kc-name">{u.username}</span>
                        <span className={`kc-badge ${u.role}`}>{u.role}</span>
                        {u.app && <span className="kc-badge system">{u.app}</span>}
                      </div>
                      <div className="kc-meta">
                        {u.store_name ? `Store: ${u.store_name}` : '無綁定 Store'} • 建立於 {new Date(u.created_at).toLocaleDateString()}
                      </div>
                    </div>
                    {canModify && (
                      <div style={{ display: 'flex', gap: '0.375rem' }}>
                        <button
                          type="button"
                          className={`btn btn-sm ${u.disabled ? 'btn-primary' : 'btn-secondary'}`}
                          style={{ padding: '0.25rem 0.5rem' }}
                          onClick={() => handleToggleDisabled(u.id, u.disabled)}
                          title={u.disabled ? '啟用' : '停用'}
                        >
                          <Power size={12} />
                        </button>
                        <button
                          type="button"
                          className="btn btn-danger btn-sm"
                          style={{ padding: '0.25rem 0.5rem' }}
                          onClick={() => handleDelete(u.id, u.username)}
                          title="刪除"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Update `App.tsx` HomeShell to fetch auth profile and wire it into UsersPanel**

Modify `HomeShell` in `frontend/src/App.tsx` to:
1. Call `api.getMe()` on mount, and store the user profile.
2. Pass `profile?.role` and `profile?.user_id` to `<UsersPanel />`.
3. Add a button to open `UsersPanel` from `Header` (e.g. wire up a menu item for Users Panel in `Header`).

Let's read `frontend/src/components/Header.tsx` to see how it can trigger opening the UsersPanel.
(Will check in Step 3/4)

**Step 3: Run build to verify TypeScript compiles**

Run: `pnpm build`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/UsersPanel.tsx
git commit -m "frontend: implement UsersPanel layout and account CRUD logic"
```

---

### Task 6: Header, Navigation, and Logout Integration

**Files:**
- Modify: `frontend/src/components/Header.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/Hciot.tsx`
- Modify: `frontend/src/pages/Jti.tsx`

**Step 1: Check existing Header parameters**

Modify `frontend/src/components/Header.tsx` to support the following:
1. Accept `userProfile` (role/username) and `onOpenUsersPanel` and `onLogout`.
2. Render "帳號管理" button in header if the user's role is `"admin"` or `"super_admin"`.
3. Render a "登出" button.
4. If in `/general`, render links "前往 HCIOT" and "前往 JTI".

Let's update `frontend/src/components/Header.tsx`:
```tsx
import { useNavigate } from 'react-router-dom';
import { LogOut, Settings, KeyRound, Users, ShieldAlert, Monitor } from 'lucide-react';
import type { UserProfile } from '../services/api/auth';
import * as api from '../services/api';

interface HeaderProps {
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  status: string;
  theme: string;
  onToggleTheme: () => void;
  canOpenConversationHistory: boolean;
  onOpenConversationHistory: () => void;
  onOpenAdminPanel: () => void;
  onOpenApiKeysPanel: () => void;
  onOpenPromptPanel: () => void;
  onOpenExtKeysPanel: () => void;
  onOpenUsersPanel?: () => void;
  userProfile?: UserProfile | null;
  onLogout?: () => void;
  onShowStatus: (msg: string) => void;
}

export default function Header({
  sidebarOpen,
  onToggleSidebar,
  status,
  theme,
  onToggleTheme,
  canOpenConversationHistory,
  onOpenConversationHistory,
  onOpenAdminPanel,
  onOpenApiKeysPanel,
  onOpenPromptPanel,
  onOpenExtKeysPanel,
  onOpenUsersPanel,
  userProfile,
  onLogout,
}: HeaderProps) {
  const navigate = useNavigate();

  const handleLogout = async () => {
    try {
      await api.logout();
      if (onLogout) onLogout();
      navigate('/login');
    } catch (err) {
      console.error(err);
      navigate('/login');
    }
  };

  const isAdmin = userProfile?.role === 'admin' || userProfile?.role === 'super_admin';

  return (
    <header className="app-header">
      <div className="header-left">
        <button className="icon-btn" onClick={onToggleSidebar}>
          <Settings size={18} />
        </button>
        <span className="logo">JTAI Control</span>
        {status && <span className="status-badge">{status}</span>}
      </div>

      <div className="header-right">
        {isAdmin && (
          <div style={{ display: 'flex', gap: '0.5rem', marginRight: '1rem' }}>
            <button className="btn btn-secondary btn-sm" onClick={() => navigate('/hciot')}>
              <Monitor size={14} style={{ marginRight: '0.25rem' }} />
              前往 HCIOT
            </button>
            <button className="btn btn-secondary btn-sm" onClick={() => navigate('/jti')}>
              <Monitor size={14} style={{ marginRight: '0.25rem' }} />
              前往 JTI
            </button>
          </div>
        )}

        {canOpenConversationHistory && (
          <button className="btn btn-secondary btn-sm" onClick={onOpenConversationHistory}>
            對話歷史
          </button>
        )}

        <button className="icon-btn" onClick={onOpenApiKeysPanel} title="Gemini Keys">
          <KeyRound size={18} />
        </button>

        {isAdmin && onOpenUsersPanel && (
          <button className="icon-btn" onClick={onOpenUsersPanel} title="帳號管理">
            <Users size={18} />
          </button>
        )}

        <button className="icon-btn" onClick={onToggleTheme}>
          {theme === 'dark' ? '☀️' : '🌙'}
        </button>

        {userProfile && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginLeft: '0.5rem' }}>
            <span className="user-profile-badge" style={{ fontSize: '0.8rem', background: 'rgba(255,255,255,0.08)', padding: '0.25rem 0.5rem', borderRadius: '0.25rem' }}>
              {userProfile.username} ({userProfile.role})
            </span>
            <button className="icon-btn danger" onClick={handleLogout} title="登出">
              <LogOut size={18} />
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
```

**Step 2: Add Logout and Redirection back buttons in Hciot.tsx and Jti.tsx**

In `frontend/src/pages/Hciot.tsx` and `frontend/src/pages/Jti.tsx`:
1. Use the auth hook / fetch `api.getMe()` to check the user profile.
2. In the corner header, if the user role is `admin` or `super_admin`, show a "返回後台" (Back to general) button pointing to `/`.
3. Show a "登出" (Logout) button in the header bar for direct logout.

Let's locate the header layout of `Hciot.tsx` and `Jti.tsx` and integrate the logout and profile indicator.
We can add standard absolute elements or modify their navigation headers to place these indicators.

**Step 3: Run build to verify TypeScript compiles**

Run: `pnpm build`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/Header.tsx frontend/src/pages/Hciot.tsx frontend/src/pages/Jti.tsx
git commit -m "frontend: integrate headers, back-to-general links, and logout controls"
```

---
