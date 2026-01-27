import type { Store, FileItem, ChatResponse, StartChatResponse } from '../types';

const API_BASE = '/api';

const STORAGE_KEYS = 'userGeminiApiKeys';
const STORAGE_ACTIVE = 'activeGeminiApiKey';

// 從 localStorage 取得目前啟用的 Gemini API Key
function getUserApiKey(): string | null {
  const activeName = localStorage.getItem(STORAGE_ACTIVE) || 'system';
  if (activeName === 'system') return null;
  try {
    const keys: { name: string; key: string }[] = JSON.parse(localStorage.getItem(STORAGE_KEYS) || '[]');
    const found = keys.find(k => k.name === activeName);
    return found?.key || null;
  } catch {
    return null;
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || response.statusText);
  }
  return response.json();
}

// 通用的 fetch 函數，自動加上 API Key header
async function fetchWithApiKey(url: string, options: RequestInit = {}): Promise<Response> {
  const apiKey = getUserApiKey();
  const headers = new Headers(options.headers || {});
  
  if (apiKey) {
    headers.set('X-Gemini-Api-Key', apiKey);
  }
  
  return fetch(url, {
    ...options,
    headers,
  });
}

export async function fetchStores(): Promise<Store[]> {
  const response = await fetchWithApiKey(`${API_BASE}/stores`);
  return handleResponse<Store[]>(response);
}

export async function createStore(name: string): Promise<Store> {
  const response = await fetchWithApiKey(`${API_BASE}/stores`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ display_name: name }),
  });
  return handleResponse<Store>(response);
}

export async function deleteStore(name: string): Promise<void> {
  const response = await fetchWithApiKey(`${API_BASE}/stores/${name}`, {
    method: 'DELETE',
  });
  await handleResponse<void>(response);
}

export async function fetchFiles(storeName: string): Promise<FileItem[]> {
  const response = await fetchWithApiKey(`${API_BASE}/stores/${storeName}/files`);
  return handleResponse<FileItem[]>(response);
}

export async function uploadFile(storeName: string, file: File): Promise<void> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetchWithApiKey(`${API_BASE}/stores/${storeName}/upload`, {
    method: 'POST',
    body: formData,
  });
  await handleResponse<void>(response);
}

export async function deleteFile(fileName: string): Promise<void> {
  const response = await fetchWithApiKey(`${API_BASE}/files/${fileName}`, {
    method: 'DELETE',
  });
  await handleResponse<void>(response);
}

export async function startChat(storeName: string): Promise<StartChatResponse> {
  const response = await fetchWithApiKey(`${API_BASE}/chat/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ store_name: storeName }),
  });
  return handleResponse<StartChatResponse>(response);
}

export async function sendMessage(text: string): Promise<ChatResponse> {
  const response = await fetchWithApiKey(`${API_BASE}/chat/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: text }),
  });
  return handleResponse<ChatResponse>(response);
}

export async function listPrompts(storeName: string): Promise<any> {
  const response = await fetch(`${API_BASE}/stores/${storeName}/prompts`);
  return handleResponse<any>(response);
}

export async function createPrompt(storeName: string, name: string, content: string): Promise<any> {
  const response = await fetch(`${API_BASE}/stores/${storeName}/prompts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, content }),
  });
  return handleResponse<any>(response);
}

export async function updatePrompt(storeName: string, promptId: string, name?: string, content?: string): Promise<any> {
  const response = await fetch(`${API_BASE}/stores/${storeName}/prompts/${promptId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, content }),
  });
  return handleResponse<any>(response);
}

export async function deletePrompt(storeName: string, promptId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/stores/${storeName}/prompts/${promptId}`, {
    method: 'DELETE',
  });
  await handleResponse<void>(response);
}

export async function setActivePrompt(storeName: string, promptId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/stores/${storeName}/prompts/active`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt_id: promptId }),
  });
  await handleResponse<void>(response);
}

export async function listApiKeys(storeName?: string): Promise<any[]> {
  const url = storeName 
    ? `${API_BASE}/keys?store_name=${encodeURIComponent(storeName)}`
    : `${API_BASE}/keys`;
  const response = await fetch(url);
  return handleResponse<any[]>(response);
}

export async function createApiKey(name: string, storeName: string): Promise<{ key: string; message: string }> {
  const response = await fetch(`${API_BASE}/keys`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ 
      name,
      store_name: storeName
    }),
  });
  return handleResponse<{ key: string; message: string }>(response);
}

export async function deleteServerApiKey(keyId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/keys/${keyId}`, {
    method: 'DELETE',
  });
  await handleResponse<void>(response);
}

// ========== 使用者 Gemini API Key 管理（多組）==========

interface SavedApiKey {
  name: string;
  key: string;
}

export function getSavedApiKeys(): SavedApiKey[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEYS) || '[]');
  } catch {
    return [];
  }
}

export function saveApiKey(name: string, key: string): void {
  const keys = getSavedApiKeys();
  const existing = keys.findIndex(k => k.name === name);
  if (existing >= 0) {
    keys[existing].key = key;
  } else {
    keys.push({ name, key });
  }
  localStorage.setItem(STORAGE_KEYS, JSON.stringify(keys));
  // 儲存後自動切換到這組
  setActiveApiKey(name);
}

export function deleteApiKey(name: string): void {
  const keys = getSavedApiKeys().filter(k => k.name !== name);
  localStorage.setItem(STORAGE_KEYS, JSON.stringify(keys));
  // 如果刪除的是當前使用中的，切回系統預設
  if (getActiveApiKeyName() === name) {
    setActiveApiKey('system');
  }
}

export function getActiveApiKeyName(): string {
  return localStorage.getItem(STORAGE_ACTIVE) || 'system';
}

export function setActiveApiKey(name: string): void {
  localStorage.setItem(STORAGE_ACTIVE, name);
}

