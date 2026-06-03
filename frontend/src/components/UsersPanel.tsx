import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { X, UserPlus, Power, Trash2 } from 'lucide-react';
import * as api from '../services/api';
import { useEscapeKey } from '../hooks/useEscapeKey';
import { useOverlayPressClose } from '../hooks/useOverlayPressClose';
import { formatKeyScope, parseKeyScope, storeMatchesKeyName } from '../utils/scope';
import AppSelect from './AppSelect';

interface UsersPanelProps {
  isOpen: boolean;
  onClose: () => void;
  currentUserRole?: string;
  currentUserId?: string | null;
}

const DEFAULT_ROLE = 'user';
const DEFAULT_SCOPE = '';
const APP_SCOPE_OPTIONS = [
  { value: 'hciot', label: 'HCIoT' },
  { value: 'jti', label: 'JTI' },
];

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function roleBadgeClass(role: string): string {
  if (role === 'super_admin') return 'role-super-admin';
  if (role === 'admin') return 'role-admin';
  return 'role-user';
}

function normalizeKeyLabels(keyNames: unknown): string[] {
  if (!Array.isArray(keyNames)) return [];
  return keyNames.map((keyName, index) => {
    if (typeof keyName === 'string' && keyName.trim()) {
      return keyName.trim();
    }
    return `Key #${index + 1}`;
  });
}

function storeMatchesScope(store: api.Store, scope: string, keyNames: string[]): boolean {
  if (!scope) return true;
  const keyName = parseKeyScope(scope);
  if (keyName !== null) {
    return storeMatchesKeyName(store, keyName, keyNames);
  }
  return (store.managed_app || 'general') === scope;
}

function isAppScope(scope: string): boolean {
  return APP_SCOPE_OPTIONS.some((option) => option.value === scope);
}

function scopeLabel(scope: string | null): string {
  if (!scope) return '未綁定範圍';
  const keyName = parseKeyScope(scope);
  if (keyName !== null) return keyName;
  const appOption = APP_SCOPE_OPTIONS.find((option) => option.value === scope);
  return appOption?.label || scope;
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
  const [keyNames, setKeyNames] = useState<string[]>([]);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState(DEFAULT_ROLE);
  const [scope, setScope] = useState(DEFAULT_SCOPE);
  const [storeName, setStoreName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const overlayPressClose = useOverlayPressClose(onClose);

  useEscapeKey(onClose, isOpen);

  const resetForm = useCallback(() => {
    setUsername('');
    setPassword('');
    setRole(DEFAULT_ROLE);
    setScope(DEFAULT_SCOPE);
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
      const [data, keyInfo] = await Promise.all([
        api.fetchStores(),
        api.getKeyInfos().catch(() => ({ count: 0, names: [] })),
      ]);
      setStores(data);
      setKeyNames(normalizeKeyLabels(keyInfo.names));
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
    const trimmedScope = scope.trim();
    if (!trimmedUsername || !password.trim()) return;
    if (role === 'user' && !trimmedScope && !trimmedStoreName) {
      setError('一般用戶需選擇帳號範圍，或綁定單一知識庫');
      return;
    }

    setLoading(true);
    setError(null);

    const payload = {
      username: trimmedUsername,
      password,
      role,
      scope: role === 'user' && trimmedScope ? trimmedScope : null,
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
  // App-scoped users (jti/hciot) are not bound to a single store: the whole app's
  // knowledge bases stay available, so we hide the per-store dropdown entirely.
  // Key scopes and the "unbound" scope still pick a specific store.
  const showStoreSelect = role === 'user' && !isAppScope(scope);
  const filteredStores = stores.filter((store) => storeMatchesScope(store, scope, keyNames));
  const canSubmit = Boolean(
    username.trim()
      && password.trim()
      && (role !== 'user' || scope.trim() || storeName.trim()),
  );

  const roleOptions = [
    { value: 'user', label: '一般用戶 (user)' },
  ];
  if (isSuperAdmin) {
    roleOptions.push(
      { value: 'admin', label: '管理者 (admin)' },
      { value: 'super_admin', label: '超級管理員 (super_admin)' },
    );
  }

  const keyScopeOptions = keyNames.map((name) => ({
    value: formatKeyScope(name),
    label: name,
  }));

  const scopeOptions = [
    { value: '', label: '不綁定範圍（只選特定知識庫）' },
    {
      label: '應用程式',
      options: APP_SCOPE_OPTIONS,
    },
  ];
  if (keyScopeOptions.length > 0) {
    scopeOptions.push({
      label: '註冊 Key',
      options: keyScopeOptions,
    });
  }

  const storeOptions = [
    {
      value: '',
      label: scope ? '不選（此範圍下所有知識庫）' : '請選擇特定知識庫',
    },
    ...filteredStores.map((s) => ({
      value: s.name,
      label: s.display_name || s.name,
    })),
  ];

  return (
    <div className="rp-overlay" {...overlayPressClose}>
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
                <AppSelect
                  className="input-base"
                  value={role}
                  onChange={(val) => {
                    setRole(val);
                    setStoreName('');
                  }}
                  options={roleOptions}
                  disabled={loading || !isSuperAdmin}
                />
              </div>

              {role === 'user' && (
                <>
                  <div className="field">
                    <label>帳號範圍</label>
                    <AppSelect
                      className="input-base"
                      value={scope}
                      onChange={(val) => {
                        setScope(val);
                        setStoreName('');
                      }}
                      options={scopeOptions}
                      disabled={loading}
                    />
                  </div>

                  {showStoreSelect && (
                    <div className="field">
                      <label>綁定知識庫名稱 (Store Name)</label>
                      <AppSelect
                        className="input-base"
                        value={storeName}
                        onChange={setStoreName}
                        options={storeOptions}
                        disabled={loading}
                      />
                    </div>
                  )}
                </>
              )}

              <button
                type="submit"
                className="btn btn-primary btn-sm"
                disabled={loading || !canSubmit}
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
                          {u.scope && (
                            <span className="kc-badge system">
                              {scopeLabel(u.scope)}
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
