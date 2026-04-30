import type {
  Store,
  FileItem,
  ChatResponse,
  StartChatResponse,
  AppTarget,
} from '../../types';
import { API_BASE, fetchAsAdmin, fetchWithApiKey, fetchWithUserGeminiKey, handleResponse } from './base';

// ========== Stores & Files ==========

export async function fetchStores(): Promise<Store[]> {
  const response = await fetchWithUserGeminiKey(`${API_BASE}/stores`);
  return handleResponse<Store[]>(response);
}

export async function createStore(name: string, keyIndex: number = 0): Promise<Store> {
  const response = await fetchWithUserGeminiKey(`${API_BASE}/stores`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ display_name: name, key_index: keyIndex }),
  });
  return handleResponse<Store>(response);
}

export async function getKeyInfos(): Promise<{ count: number; names: string[] }> {
  const response = await fetchWithUserGeminiKey(`${API_BASE}/keys/count`);
  return handleResponse<{ count: number; names: string[] }>(response);
}

export async function deleteStore(name: string): Promise<void> {
  const response = await fetchWithUserGeminiKey(`${API_BASE}/stores/${name}`, { method: 'DELETE' });
  await handleResponse<void>(response);
}

export async function fetchFiles(storeName: string): Promise<FileItem[]> {
  const response = await fetchWithUserGeminiKey(`${API_BASE}/stores/${storeName}/files`);
  return handleResponse<FileItem[]>(response);
}

// ========== Knowledge Management ==========

function knowledgeParams(appTarget: AppTarget, language: string): URLSearchParams {
  const normalizedLanguage = language.toLowerCase().startsWith('en') ? 'en' : 'zh';
  return new URLSearchParams({ app: appTarget, language: normalizedLanguage });
}

function knowledgeFileUrl(filename: string, suffix: string, appTarget: AppTarget, language: string): string {
  return `${API_BASE}/knowledge/files/${encodeURIComponent(filename)}${suffix}?${knowledgeParams(appTarget, language)}`;
}

export async function listManagedKnowledgeFiles(appTarget: AppTarget, language: string = 'zh'): Promise<any> {
  const response = await fetchAsAdmin(`${API_BASE}/knowledge/files/?${knowledgeParams(appTarget, language)}`);
  return handleResponse<any>(response);
}

export async function getManagedKnowledgeFileContent(appTarget: AppTarget, filename: string, language: string = 'zh'): Promise<any> {
  const response = await fetchAsAdmin(knowledgeFileUrl(filename, '/content', appTarget, language));
  return handleResponse<any>(response);
}

export function downloadManagedKnowledgeFile(appTarget: AppTarget, filename: string, language: string = 'zh'): void {
  window.open(knowledgeFileUrl(filename, '/download', appTarget, language), '_blank');
}

export async function updateManagedKnowledgeFileContent(
  appTarget: AppTarget,
  filename: string,
  content: string,
  language: string = 'zh',
): Promise<any> {
  const response = await fetchAsAdmin(knowledgeFileUrl(filename, '/content', appTarget, language), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });
  return handleResponse<any>(response);
}

export async function uploadManagedKnowledgeFile(appTarget: AppTarget, language: string, file: File): Promise<any> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetchAsAdmin(`${API_BASE}/knowledge/upload/?${knowledgeParams(appTarget, language)}`, {
    method: 'POST',
    body: formData,
  });
  return handleResponse<any>(response);
}

export async function deleteManagedKnowledgeFile(appTarget: AppTarget, fileName: string, language: string = 'zh'): Promise<any> {
  const response = await fetchAsAdmin(knowledgeFileUrl(fileName, '', appTarget, language), {
    method: 'DELETE',
  });
  return handleResponse<any>(response);
}

// ========== Chat ==========

function getSelectedModel(): string {
  return localStorage.getItem('selectedModel') || 'gemini-2.5-flash-lite';
}

export async function startChat(storeName: string, previousSessionId?: string | null): Promise<StartChatResponse> {
  const response = await fetchWithUserGeminiKey(`${API_BASE}/chat/start`, {
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
  const response = await fetchWithUserGeminiKey(`${API_BASE}/chat/message`, {
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
    const raw = JSON.parse(localStorage.getItem('userGeminiApiKeys') || '[]');
    if (!Array.isArray(raw)) return [];
    return raw
      .map((item: any) => ({
        name: String(item?.name || '').trim(),
        key: String(item?.key || '').trim(),
      }))
      .filter(item => item.name && item.key);
  } catch {
    return [];
  }
}

export function saveApiKey(name: string, key: string): void {
  const normalizedName = (name || '').trim();
  const normalizedKey = (key || '').trim();
  if (!normalizedName || !normalizedKey) return;

  const keys = getSavedApiKeys();
  const existing = keys.findIndex(k => k.name === normalizedName);
  if (existing >= 0) {
    keys[existing].key = normalizedKey;
  } else {
    keys.push({ name: normalizedName, key: normalizedKey });
  }
  localStorage.setItem('userGeminiApiKeys', JSON.stringify(keys));
  setActiveApiKey(normalizedName);
}

export function deleteApiKey(name: string): void {
  const normalizedName = (name || '').trim();
  const keys = getSavedApiKeys().filter(k => k.name !== normalizedName);
  localStorage.setItem('userGeminiApiKeys', JSON.stringify(keys));
  if (getActiveApiKeyName() === normalizedName) {
    setActiveApiKey('system');
  }
}

export function getActiveApiKeyName(): string {
  const active = (localStorage.getItem('activeGeminiApiKey') || 'system').trim();
  return active || 'system';
}

export function setActiveApiKey(name: string): void {
  const normalizedName = (name || '').trim();
  localStorage.setItem('activeGeminiApiKey', normalizedName || 'system');
}

// ========== General Chat Conversations ==========

export async function getGeneralConversations(storeName?: string): Promise<any> {
  const params = storeName ? `?store_name=${encodeURIComponent(storeName)}` : '';
  const response = await fetchWithUserGeminiKey(`${API_BASE}/chat/history${params}`);
  return handleResponse<any>(response);
}

export async function getGeneralConversationDetail(sessionId: string): Promise<any> {
  const response = await fetchWithUserGeminiKey(`${API_BASE}/chat/history/${encodeURIComponent(sessionId)}`);
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
  const doFetch = mode === 'general' ? fetchWithUserGeminiKey : fetchAsAdmin;
  const response = await doFetch(url, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_ids: sessionIds }),
  });
  await handleResponse<void>(response);
}

// ========== RAG Admin ==========

export type RagSourceType = 'hciot' | 'jti' | 'all';

export interface ReindexRagResponse {
  started: boolean;
  source_types: string[];
  languages: string[];
}

async function reindexRag(sourceType: RagSourceType): Promise<ReindexRagResponse> {
  const query = new URLSearchParams({ source_type: sourceType });
  const response = await fetchAsAdmin(API_BASE + '/admin/rag/reindex?' + query.toString(), {
    method: 'POST',
  });
  return handleResponse<ReindexRagResponse>(response);
}
export default reindexRag;
