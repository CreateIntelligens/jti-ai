import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { X, UserPlus, Power, Trash2 } from 'lucide-react';
import * as api from '../services/api';
import { useEscapeKey } from '../hooks/useEscapeKey';

interface UsersPanelProps {
  isOpen: boolean;
  onClose: () => void;
  currentUserRole?: string;
  currentUserId?: string | null;
}

const DEFAULT_ROLE = 'user';
const DEFAULT_APP = 'hciot';

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function roleBadgeClass(role: string): string {
  if (role === 'super_admin') return 'role-super-admin';
  if (role === 'admin') return 'role-admin';
  return 'role-user';
}

function canModifyAccount(
  currentUserRole: string,
  currentUserId: string | null | undefined,
  user: api.UserAccount,
): boolean {
  if (user.id === currentUserId) return false;
  if (currentUserRole === 'super_admin') return true;
  return currentUserRole === 'admin' && user.role === 'user';
}

export default function UsersPanel({ isOpen, onClose, currentUserRole = 'admin', currentUserId }: UsersPanelProps) {
  const [users, setUsers] = useState<api.UserAccount[]>([]);
  const [stores, setStores] = useState<api.Store[]>([]);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState(DEFAULT_ROLE);
  const [app, setApp] = useState(DEFAULT_APP);
  const [storeName, setStoreName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEscapeKey(onClose, isOpen);

  const resetForm = useCallback(() => {
    setUsername('');
    setPassword('');
    setRole(DEFAULT_ROLE);
    setApp(DEFAULT_APP);
    setStoreName('');
    setError(null);
  }, []);

  const loadUsers = useCallback(async () => {
    try {
      const data = await api.listUsers();
      setUsers(data);
    } catch (err: unknown) {
      setError(errorMessage(err, '無法獲取帳號列表'));
    }
  }, []);

  const loadStores = useCallback(async () => {
    try {
      const data = await api.fetchStores();
      setStores(data);
    } catch (err: unknown) {
      console.error('無法獲取知識庫列表', err);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      void loadUsers();
      void loadStores();
      resetForm();
    }
  }, [isOpen, loadUsers, loadStores, resetForm]);

  if (!isOpen) return null;

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    const trimmedUsername = username.trim();
    const trimmedStoreName = storeName.trim();
    if (!trimmedUsername || !password.trim()) return;

    setLoading(true);
    setError(null);

    const payload = {
      username: trimmedUsername,
      password,
      role,
      app: role === 'user' ? app : null,
      store_name: role === 'user' && trimmedStoreName ? trimmedStoreName : null,
    };

    try {
      await api.createUser(payload);
      setUsername('');
      setPassword('');
      setStoreName('');
      void loadUsers();
    } catch (err: unknown) {
      setError(errorMessage(err, '建立帳號失敗'));
    } finally {
      setLoading(false);
    }
  };

  const handleToggleDisabled = async (userId: string, currentStatus: boolean) => {
    try {
      setError(null);
      await api.setUserDisabled(userId, !currentStatus);
      void loadUsers();
    } catch (err: unknown) {
      setError(errorMessage(err, '切換啟用狀態失敗'));
    }
  };

  const handleDelete = async (userId: string, name: string) => {
    if (!window.confirm(`確定要刪除「${name}」帳號嗎？此操作無法復原。`)) return;
    try {
      setError(null);
      await api.deleteUser(userId);
      void loadUsers();
    } catch (err: unknown) {
      setError(errorMessage(err, '刪除帳號失敗'));
    }
  };

  const isSuperAdmin = currentUserRole === 'super_admin';

  return (
    <div className="rp-overlay" onClick={onClose}>
      <div className="rp-panel" onClick={(e) => e.stopPropagation()}>
        <div className="rp-header">
          <span className="rp-title">帳號管理</span>
          <button className="icon-btn" onClick={onClose} aria-label="關閉"><X size={18} /></button>
        </div>

        <div className="rp-body users-panel-body">
          <div>
            <div className="rp-section-title">新增帳號</div>
            <form onSubmit={handleCreate} className="rp-form-stack users-panel-form">
              {error && (
                <div className="users-panel-error">
                  {error}
                </div>
              )}

              <div className="field">
                <label>使用者名稱</label>
                <input
                  className="input-base"
                  placeholder="請輸入帳號名稱"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  disabled={loading}
                />
              </div>

              <div className="field">
                <label>密碼</label>
                <input
                  className="input-base"
                  type="password"
                  placeholder="請輸入密碼"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  disabled={loading}
                />
              </div>

              <div className="field">
                <label>角色類型</label>
                <select
                  className="select-reset input-base"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  disabled={loading || !isSuperAdmin}
                >
                  <option value="user">一般用戶 (user)</option>
                  {isSuperAdmin && (
                    <>
                      <option value="admin">管理者 (admin)</option>
                      <option value="super_admin">超級管理員 (super_admin)</option>
                    </>
                  )}
                </select>
              </div>

              {role === 'user' && (
                <>
                  <div className="field">
                    <label>綁定應用程式 (App)</label>
                    <select
                      className="select-reset input-base"
                      value={app}
                      onChange={(e) => {
                        const newApp = e.target.value;
                        setApp(newApp);
                        setStoreName('');
                      }}
                      disabled={loading}
                    >
                      <option value="hciot">hciot</option>
                      <option value="jti">jti</option>
                    </select>
                  </div>

                  <div className="field">
                    <label>綁定知識庫名稱 (Store Name)</label>
                    <select
                      className="select-reset input-base"
                      value={storeName}
                      onChange={(e) => setStoreName(e.target.value)}
                      disabled={loading}
                    >
                      <option value="">不選（此 App 下所有知識庫）</option>
                      {stores
                        .filter((s) => (s.managed_app || 'general') === app)
                        .map((s) => (
                          <option key={s.name} value={s.name}>
                            {s.display_name || s.name}
                          </option>
                        ))}
                    </select>
                  </div>
                </>
              )}

              <button
                type="submit"
                className="btn btn-primary btn-sm"
                disabled={loading || !username.trim() || !password.trim()}
              >
                <UserPlus size={14} />
                {loading ? '建立中...' : '建立帳號'}
              </button>
            </form>
          </div>

          <div className="sep-row">
            <div className="sep-line" />
            <span className="sep-label">帳號列表</span>
            <div className="sep-line" />
          </div>

          <div className="users-panel-list-wrap">
            <div className="rp-stack users-panel-list">
              {users.length === 0 ? (
                <div className="rp-list-empty">尚無帳號資料</div>
              ) : (
                users.map((u) => {
                  const isSelf = u.id === currentUserId;
                  const canModify = canModifyAccount(currentUserRole, currentUserId, u);
                  const cardClassName = [
                    'key-card',
                    'users-panel-card',
                    u.disabled ? 'is-disabled' : '',
                    isSelf ? 'is-self' : '',
                  ].filter(Boolean).join(' ');

                  return (
                    <div
                      key={u.id}
                      className={cardClassName}
                    >
                      <div className="kc-info">
                        <div className="kc-name-row users-panel-name-row">
                          <span className="kc-name users-panel-name">{u.username}</span>
                          <span className={`kc-badge ${roleBadgeClass(u.role)}`}>
                            {u.role}
                          </span>
                          {u.app && (
                            <span className="kc-badge system">
                              {u.app}
                            </span>
                          )}
                          {isSelf && (
                            <span className="kc-badge self">
                              你
                            </span>
                          )}
                        </div>
                        <div className="kc-meta users-panel-meta">
                          {u.store_name ? `Store: ${u.store_name}` : '無綁定 Store'} • 建立於 {new Date(u.created_at).toLocaleDateString()}
                        </div>
                      </div>

                      {canModify && (
                        <div className="users-panel-actions">
                          <button
                            type="button"
                            className={`btn btn-sm ${u.disabled ? 'btn-primary' : 'btn-secondary'}`}
                            onClick={() => handleToggleDisabled(u.id, u.disabled)}
                            title={u.disabled ? '啟用帳號' : '停用帳號'}
                          >
                            <Power size={12} />
                          </button>
                          <button
                            type="button"
                            className="btn btn-danger btn-sm"
                            onClick={() => handleDelete(u.id, u.username)}
                            title="刪除帳號"
                          >
                            <Trash2 size={12} />
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
