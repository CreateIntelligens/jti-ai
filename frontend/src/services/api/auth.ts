import { API_BASE, handleResponse } from './base';

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
  return handleResponse<LoginResponse>(response);
}

export async function logout(): Promise<LogoutResponse> {
  const response = await fetch(`${API_BASE}/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  });
  return handleResponse<LogoutResponse>(response);
}

export async function getMe(): Promise<UserProfile> {
  const response = await fetch(`${API_BASE}/auth/me`, {
    credentials: 'include',
  });
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
