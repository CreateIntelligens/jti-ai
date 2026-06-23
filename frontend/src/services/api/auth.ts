import { API_BASE, handleResponse } from './base';

const SESSION_HINT_KEY = 'jtai:auth-session-known';

function readSessionStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function hasKnownAuthSession(): boolean {
  return readSessionStorage()?.getItem(SESSION_HINT_KEY) === '1';
}

function rememberAuthSession(): void {
  readSessionStorage()?.setItem(SESSION_HINT_KEY, '1');
}

function forgetAuthSession(): void {
  readSessionStorage()?.removeItem(SESSION_HINT_KEY);
}

export interface UserProfile {
  user_id: string | null;
  username: string | null;
  role: string;
  scope: string | null;
  store_name: string | null;
}

export interface LoginResponse {
  token: string;
  role: string;
  scope: string | null;
}

export interface LogoutResponse {
  ok: boolean;
}

export interface UserAccount {
  id: string;
  username: string;
  role: string;
  scope: string | null;
  store_name: string | null;
  disabled: boolean;
  created_by?: string | null;
  created_at: string;
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ username, password }),
  });
  const result = await handleResponse<LoginResponse>(response);
  rememberAuthSession();
  return result;
}

export async function logout(): Promise<LogoutResponse> {
  try {
    const response = await fetch(`${API_BASE}/auth/logout`, {
      method: 'POST',
      credentials: 'include',
    });
    return await handleResponse<LogoutResponse>(response);
  } finally {
    forgetAuthSession();
  }
}

export async function getMe(): Promise<UserProfile> {
  const response = await fetch(`${API_BASE}/auth/me`, {
    credentials: 'include',
  });
  if (response.ok) {
    const profile = await response.json() as UserProfile;
    rememberAuthSession();
    return profile;
  }
  if (response.status === 401) {
    forgetAuthSession();
  }
  return handleResponse<UserProfile>(response);
}

export async function listUsers(): Promise<UserAccount[]> {
  const response = await fetch(`${API_BASE}/users`, {
    credentials: 'include',
  });
  return handleResponse<UserAccount[]>(response);
}

export async function createUser(data: {
  username: string;
  password: string;
  role: string;
  scope: string | null;
  store_name: string | null;
}): Promise<UserAccount> {
  const response = await fetch(`${API_BASE}/users`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });
  return handleResponse<UserAccount>(response);
}

export async function setUserDisabled(userId: string, disabled: boolean): Promise<UserAccount> {
  const response = await fetch(`${API_BASE}/users/${userId}/disabled`, {
    method: 'PATCH',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ disabled }),
  });
  return handleResponse<UserAccount>(response);
}

export async function deleteUser(userId: string): Promise<{ message: string }> {
  const response = await fetch(`${API_BASE}/users/${userId}`, {
    method: 'DELETE',
    credentials: 'include',
  });
  return handleResponse<{ message: string }>(response);
}
