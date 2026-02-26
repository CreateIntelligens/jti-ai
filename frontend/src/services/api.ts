import type { Store, FileItem, ChatResponse, StartChatResponse } from '../types';

const API_BASE = '/api';

const STORAGE_KEYS = 'userGeminiApiKeys';
const STORAGE_ACTIVE = 'activeGeminiApiKey';

// 從 localStorage 取得目前啟用的 API Key（用於呼叫後端 API）
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

// 通用的 fetch 函數，自動加上 API-Token header
export async function fetchWithApiKey(url: string, options: RequestInit = {}): Promise<Response> {
  const apiKey = getUserApiKey();
  const headers = new Headers(options.headers || {});

  if (apiKey) {
    headers.set('API-Token', apiKey);
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

// 取得目前選擇的模型
function getSelectedModel(): string {
  return localStorage.getItem('selectedModel') || 'gemini-2.5-flash';
}

export async function startChat(storeName: string, previousSessionId?: string | null): Promise<StartChatResponse> {
  const response = await fetchWithApiKey(`${API_BASE}/chat/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ store_name: storeName, model: getSelectedModel(), previous_session_id: previousSessionId || undefined }),
  });
  return handleResponse<StartChatResponse>(response);
}

export async function sendMessage(text: string, sessionId?: string, turnNumber?: number): Promise<ChatResponse> {
  const payload: Record<string, unknown> = { message: text };
  if (sessionId) {
    payload.session_id = sessionId;
  }
  if (turnNumber !== undefined) {
    payload.turn_number = turnNumber;
  }

  const response = await fetchWithApiKey(`${API_BASE}/chat/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse<ChatResponse>(response);
}

export async function listPrompts(storeName: string): Promise<any> {
  const response = await fetchWithApiKey(`${API_BASE}/stores/${storeName}/prompts`);
  return handleResponse<any>(response);
}

export async function createPrompt(storeName: string, name: string, content: string): Promise<any> {
  const response = await fetchWithApiKey(`${API_BASE}/stores/${storeName}/prompts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, content }),
  });
  return handleResponse<any>(response);
}

export async function updatePrompt(storeName: string, promptId: string, name?: string, content?: string): Promise<any> {
  const response = await fetchWithApiKey(`${API_BASE}/stores/${storeName}/prompts/${promptId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, content }),
  });
  return handleResponse<any>(response);
}

export async function deletePrompt(storeName: string, promptId: string): Promise<void> {
  const response = await fetchWithApiKey(`${API_BASE}/stores/${storeName}/prompts/${promptId}`, {
    method: 'DELETE',
  });
  await handleResponse<void>(response);
}

export async function setActivePrompt(storeName: string, promptId: string | null): Promise<void> {
  const response = await fetchWithApiKey(`${API_BASE}/stores/${storeName}/prompts/active`, {
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
  const response = await fetchWithApiKey(url);
  return handleResponse<any[]>(response);
}

export async function createApiKey(name: string, storeName: string, promptIndex?: number | null): Promise<{ key: string; message: string }> {
  const body: Record<string, unknown> = { name, store_name: storeName };
  if (promptIndex != null) body.prompt_index = promptIndex;
  const response = await fetchWithApiKey(`${API_BASE}/keys`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return handleResponse<{ key: string; message: string }>(response);
}

export async function deleteServerApiKey(keyId: string): Promise<void> {
  const response = await fetchWithApiKey(`${API_BASE}/keys/${keyId}`, {
    method: 'DELETE',
  });
  await handleResponse<void>(response);
}

// ========== JTI Prompt Management ==========

export interface JtiRuntimeSettings {
  response_rule_sections: {
    zh: {
      role_scope: string;
      scope_limits: string;
      response_style: string;
      knowledge_rules: string;
    };
    en: {
      role_scope: string;
      scope_limits: string;
      response_style: string;
      knowledge_rules: string;
    };
  };
  welcome: {
    zh: {
      title: string;
      description: string;
    };
    en: {
      title: string;
      description: string;
    };
  };
  max_response_chars: number;
}

export interface JtiRuntimeSettingsResponse {
  prompt_id?: string;
  settings: JtiRuntimeSettings;
}

export async function listJtiPrompts(): Promise<any> {
  const response = await fetchWithApiKey(`${API_BASE}/jti/prompts/`);
  return handleResponse<any>(response);
}

export async function createJtiPrompt(name: string, content: string): Promise<any> {
  const response = await fetchWithApiKey(`${API_BASE}/jti/prompts/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, content }),
  });
  return handleResponse<any>(response);
}

export async function updateJtiPrompt(promptId: string, name?: string, content?: string): Promise<any> {
  const response = await fetchWithApiKey(`${API_BASE}/jti/prompts/${promptId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, content }),
  });
  return handleResponse<any>(response);
}

export async function deleteJtiPrompt(promptId: string): Promise<void> {
  const response = await fetchWithApiKey(`${API_BASE}/jti/prompts/${promptId}`, {
    method: 'DELETE',
  });
  await handleResponse<void>(response);
}

export async function setActiveJtiPrompt(promptId: string | null): Promise<void> {
  const response = await fetchWithApiKey(`${API_BASE}/jti/prompts/active`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt_id: promptId }),
  });
  await handleResponse<void>(response);
}

export async function cloneDefaultJtiPrompt(): Promise<any> {
  const response = await fetchWithApiKey(`${API_BASE}/jti/prompts/clone`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  return handleResponse<any>(response);
}

export async function getJtiRuntimeSettings(promptId?: string): Promise<JtiRuntimeSettingsResponse> {
  const query = promptId ? `?prompt_id=${encodeURIComponent(promptId)}` : '';
  const response = await fetchWithApiKey(`${API_BASE}/jti/prompts/runtime-settings${query}`, {
    method: 'GET',
  });
  return handleResponse<JtiRuntimeSettingsResponse>(response);
}

export async function updateJtiRuntimeSettings(
  settings: JtiRuntimeSettings,
  promptId?: string,
): Promise<{ settings: JtiRuntimeSettings; message: string; prompt_id?: string }> {
  const payload = promptId ? { ...settings, prompt_id: promptId } : settings;
  const response = await fetchWithApiKey(`${API_BASE}/jti/prompts/runtime-settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse<{ settings: JtiRuntimeSettings; message: string; prompt_id?: string }>(response);
}
// ========== JTI 知識庫管理 ==========

export async function listJtiKnowledgeFiles(language: string = 'zh'): Promise<any> {
  const response = await fetchWithApiKey(`${API_BASE}/jti/knowledge/files/?language=${language}`);
  return handleResponse<any>(response);
}

export async function getJtiKnowledgeFileContent(filename: string, language: string = 'zh'): Promise<any> {
  const response = await fetchWithApiKey(`${API_BASE}/jti/knowledge/files/${encodeURIComponent(filename)}/content?language=${language}`);
  return handleResponse<any>(response);
}

export async function downloadJtiKnowledgeFile(filename: string, language: string = 'zh'): Promise<void> {
  const url = `${API_BASE}/jti/knowledge/files/${encodeURIComponent(filename)}/download?language=${language}`;
  const response = await fetchWithApiKey(url);
  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || response.statusText);
  }
  const blob = await response.blob();
  const objectUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(objectUrl);
}

export async function updateJtiKnowledgeFileContent(filename: string, content: string, language: string = 'zh'): Promise<any> {
  const response = await fetchWithApiKey(`${API_BASE}/jti/knowledge/files/${encodeURIComponent(filename)}/content?language=${language}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });
  return handleResponse<any>(response);
}

export async function uploadJtiKnowledgeFile(language: string, file: File): Promise<any> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetchWithApiKey(`${API_BASE}/jti/knowledge/upload/?language=${language}`, {
    method: 'POST',
    body: formData,
  });
  return handleResponse<any>(response);
}

export async function deleteJtiKnowledgeFile(fileName: string, language: string = 'zh'): Promise<any> {
  const response = await fetchWithApiKey(`${API_BASE}/jti/knowledge/files/${encodeURIComponent(fileName)}?language=${language}`, {
    method: 'DELETE',
  });
  return handleResponse<any>(response);
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

// ========== General Chat Conversations ==========

export async function getGeneralConversations(storeName?: string): Promise<any> {
  const params = storeName ? `?store_name=${encodeURIComponent(storeName)}` : '';
  const response = await fetchWithApiKey(`${API_BASE}/chat/history${params}`);
  return handleResponse<any>(response);
}

export async function getGeneralConversationDetail(sessionId: string): Promise<any> {
  const response = await fetchWithApiKey(`${API_BASE}/chat/history/${encodeURIComponent(sessionId)}`);
  return handleResponse<any>(response);
}

export async function deleteConversations(mode: 'jti' | 'general', sessionIds: string[]): Promise<void> {
  const url = mode === 'jti'
    ? `${API_BASE}/jti/history`
    : `${API_BASE}/chat/history`;
  const response = await fetchWithApiKey(url, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_ids: sessionIds }),
  });
  await handleResponse<void>(response);
}
