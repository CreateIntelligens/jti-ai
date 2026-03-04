import type {
  Store,
  FileItem,
  ChatResponse,
  StartChatResponse,
  CmsAppTarget,
} from '../../types';
import { API_BASE, fetchAsAdmin, fetchWithApiKey, handleResponse } from './base';

// ========== Stores & Files ==========

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
  const response = await fetchWithApiKey(`${API_BASE}/stores/${name}`, { method: 'DELETE' });
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
  const response = await fetchWithApiKey(`${API_BASE}/files/${fileName}`, { method: 'DELETE' });
  await handleResponse<void>(response);
}

// ========== Homepage CMS Knowledge ==========

function normalizeKnowledgeLanguage(language: string): string {
  return language.toLowerCase().startsWith('en') ? 'en' : 'zh';
}

export async function listManagedKnowledgeFiles(appTarget: CmsAppTarget, language: string = 'zh'): Promise<any> {
  const params = new URLSearchParams({ app: appTarget, language: normalizeKnowledgeLanguage(language) });
  const response = await fetchAsAdmin(`${API_BASE}/admin/knowledge/files/?${params}`);
  return handleResponse<any>(response);
}

export async function getManagedKnowledgeFileContent(appTarget: CmsAppTarget, filename: string, language: string = 'zh'): Promise<any> {
  const params = new URLSearchParams({ app: appTarget, language: normalizeKnowledgeLanguage(language) });
  const response = await fetchAsAdmin(`${API_BASE}/admin/knowledge/files/${encodeURIComponent(filename)}/content?${params}`);
  return handleResponse<any>(response);
}

export function downloadManagedKnowledgeFile(appTarget: CmsAppTarget, filename: string, language: string = 'zh'): void {
  const params = new URLSearchParams({ app: appTarget, language: normalizeKnowledgeLanguage(language) });
  window.open(`${API_BASE}/admin/knowledge/files/${encodeURIComponent(filename)}/download?${params}`, '_blank');
}

export async function updateManagedKnowledgeFileContent(
  appTarget: CmsAppTarget,
  filename: string,
  content: string,
  language: string = 'zh',
): Promise<any> {
  const params = new URLSearchParams({ app: appTarget, language: normalizeKnowledgeLanguage(language) });
  const response = await fetchAsAdmin(`${API_BASE}/admin/knowledge/files/${encodeURIComponent(filename)}/content?${params}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });
  return handleResponse<any>(response);
}

export async function uploadManagedKnowledgeFile(appTarget: CmsAppTarget, language: string, file: File): Promise<any> {
  const formData = new FormData();
  formData.append('file', file);
  const params = new URLSearchParams({ app: appTarget, language: normalizeKnowledgeLanguage(language) });
  const response = await fetchAsAdmin(`${API_BASE}/admin/knowledge/upload/?${params}`, {
    method: 'POST',
    body: formData,
  });
  return handleResponse<any>(response);
}

export async function deleteManagedKnowledgeFile(appTarget: CmsAppTarget, fileName: string, language: string = 'zh'): Promise<any> {
  const params = new URLSearchParams({ app: appTarget, language: normalizeKnowledgeLanguage(language) });
  const response = await fetchAsAdmin(`${API_BASE}/admin/knowledge/files/${encodeURIComponent(fileName)}?${params}`, {
    method: 'DELETE',
  });
  return handleResponse<any>(response);
}

// ========== Chat ==========

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
  if (sessionId) payload.session_id = sessionId;
  if (turnNumber !== undefined) payload.turn_number = turnNumber;
  const response = await fetchWithApiKey(`${API_BASE}/chat/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse<ChatResponse>(response);
}

// ========== Prompts ==========

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
  const response = await fetchWithApiKey(`${API_BASE}/stores/${storeName}/prompts/${promptId}`, { method: 'DELETE' });
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

// ========== Server API Keys ==========

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
  const response = await fetchWithApiKey(`${API_BASE}/keys/${keyId}`, { method: 'DELETE' });
  await handleResponse<void>(response);
}

// ========== User Gemini API Keys (localStorage) ==========

interface SavedApiKey {
  name: string;
  key: string;
}

export function getSavedApiKeys(): SavedApiKey[] {
  try {
    return JSON.parse(localStorage.getItem('userGeminiApiKeys') || '[]');
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
  localStorage.setItem('userGeminiApiKeys', JSON.stringify(keys));
  setActiveApiKey(name);
}

export function deleteApiKey(name: string): void {
  const keys = getSavedApiKeys().filter(k => k.name !== name);
  localStorage.setItem('userGeminiApiKeys', JSON.stringify(keys));
  if (getActiveApiKeyName() === name) {
    setActiveApiKey('system');
  }
}

export function getActiveApiKeyName(): string {
  return localStorage.getItem('activeGeminiApiKey') || 'system';
}

export function setActiveApiKey(name: string): void {
  localStorage.setItem('activeGeminiApiKey', name);
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

export async function deleteConversations(mode: 'jti' | 'hciot' | 'general', sessionIds: string[]): Promise<void> {
  let url: string;
  switch (mode) {
    case 'jti':
      url = `${API_BASE}/jti-admin/conversations`;
      break;
    case 'hciot':
      url = `${API_BASE}/hciot-admin/conversations`;
      break;
    default:
      url = `${API_BASE}/chat/history`;
      break;
  }
  const doFetch = mode === 'general' ? fetchWithApiKey : fetchAsAdmin;
  const response = await doFetch(url, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_ids: sessionIds }),
  });
  await handleResponse<void>(response);
}
