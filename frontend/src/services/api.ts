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

export async function listJtiPrompts(language: string = 'zh'): Promise<any> {
  const normalizedLanguage = language.toLowerCase().startsWith('en') ? 'en' : 'zh';
  const response = await fetchWithApiKey(`${API_BASE}/jti/prompts/?language=${normalizedLanguage}`);
  return handleResponse<any>(response);
}

export async function createJtiPrompt(name: string, content: string, language: string = 'zh'): Promise<any> {
  const normalizedLanguage = language.toLowerCase().startsWith('en') ? 'en' : 'zh';
  const response = await fetchWithApiKey(`${API_BASE}/jti/prompts/?language=${normalizedLanguage}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, content }),
  });
  return handleResponse<any>(response);
}

export async function updateJtiPrompt(
  promptId: string,
  name?: string,
  content?: string,
  language: string = 'zh',
): Promise<any> {
  const normalizedLanguage = language.toLowerCase().startsWith('en') ? 'en' : 'zh';
  const response = await fetchWithApiKey(`${API_BASE}/jti/prompts/${promptId}?language=${normalizedLanguage}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, content }),
  });
  return handleResponse<any>(response);
}

export async function deleteJtiPrompt(promptId: string, language: string = 'zh'): Promise<void> {
  const normalizedLanguage = language.toLowerCase().startsWith('en') ? 'en' : 'zh';
  const response = await fetchWithApiKey(`${API_BASE}/jti/prompts/${promptId}?language=${normalizedLanguage}`, {
    method: 'DELETE',
  });
  await handleResponse<void>(response);
}

export async function setActiveJtiPrompt(promptId: string | null, language: string = 'zh'): Promise<void> {
  const normalizedLanguage = language.toLowerCase().startsWith('en') ? 'en' : 'zh';
  const response = await fetchWithApiKey(`${API_BASE}/jti/prompts/active?language=${normalizedLanguage}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt_id: promptId }),
  });
  await handleResponse<void>(response);
}

export async function cloneDefaultJtiPrompt(language: string = 'zh'): Promise<any> {
  const normalizedLanguage = language.toLowerCase().startsWith('en') ? 'en' : 'zh';
  const response = await fetchWithApiKey(`${API_BASE}/jti/prompts/clone?language=${normalizedLanguage}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  return handleResponse<any>(response);
}

export async function getJtiRuntimeSettings(
  promptId?: string,
  language: string = 'zh',
): Promise<JtiRuntimeSettingsResponse> {
  const normalizedLanguage = language.toLowerCase().startsWith('en') ? 'en' : 'zh';
  const query = new URLSearchParams({ language: normalizedLanguage });
  if (promptId) {
    query.set('prompt_id', promptId);
  }
  const response = await fetchWithApiKey(`${API_BASE}/jti/prompts/runtime-settings?${query.toString()}`, {
    method: 'GET',
  });
  return handleResponse<JtiRuntimeSettingsResponse>(response);
}

export async function updateJtiRuntimeSettings(
  settings: JtiRuntimeSettings,
  promptId?: string,
  language: string = 'zh',
): Promise<{ settings: JtiRuntimeSettings; message: string; prompt_id?: string }> {
  const normalizedLanguage = language.toLowerCase().startsWith('en') ? 'en' : 'zh';
  const payload = promptId ? { ...settings, prompt_id: promptId } : settings;
  const response = await fetchWithApiKey(`${API_BASE}/jti/prompts/runtime-settings?language=${normalizedLanguage}`, {
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
  const apiKey = getUserApiKey();
  const params = new URLSearchParams({ language });
  if (apiKey) params.set('token', apiKey);
  window.open(`${API_BASE}/jti/knowledge/files/${encodeURIComponent(filename)}/download?${params}`, '_blank');
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

// ========== JTI 題庫管理 ==========

export interface QuizQuestionOption {
  id: string;
  text: string;
  score: Record<string, number>;
}

export interface QuizQuestion {
  id: string;
  text: string;
  category: string;
  weight: number;
  options: QuizQuestionOption[];
}

export interface QuizBank {
  bank_id: string;
  name: string;
  language: string;
  is_active: boolean;
  is_default: boolean;
  question_count: number;
  quiz_id?: string;
  title?: string;
  description?: string;
}

export interface QuizBankMetadata {
  bank_id: string;
  name: string;
  quiz_id: string;
  title: string;
  description: string;
  total_questions: number;
  dimensions: string[];
  tie_breaker_priority: string[];
  selection_rules: {
    total: number;
    required: { personality: number; random_from: string[] };
  };
  is_active: boolean;
  is_default: boolean;
}

export interface ColorResult {
  color_id: string;
  title: string;
  color_name: string;
  recommended_colors: string[];
  description: string;
}

export interface QuizBankStats {
  total_questions: number;
  categories: Record<string, number>;
  dimensions: string[];
  selection_rules: Record<string, unknown>;
}

// --- Bank Management ---

export async function listQuizBanks(language: string = 'zh'): Promise<{ banks: QuizBank[]; total: number; max: number }> {
  const response = await fetchWithApiKey(`${API_BASE}/jti/quiz-bank/banks/?language=${language}`);
  return handleResponse(response);
}

export async function createQuizBank(language: string, name: string): Promise<QuizBank> {
  const response = await fetchWithApiKey(`${API_BASE}/jti/quiz-bank/banks/?language=${language}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  return handleResponse(response);
}

export async function deleteQuizBank(language: string, bankId: string): Promise<void> {
  const response = await fetchWithApiKey(`${API_BASE}/jti/quiz-bank/banks/${encodeURIComponent(bankId)}?language=${language}`, {
    method: 'DELETE',
  });
  await handleResponse(response);
}

export async function activateQuizBank(language: string, bankId: string): Promise<void> {
  const response = await fetchWithApiKey(`${API_BASE}/jti/quiz-bank/banks/${encodeURIComponent(bankId)}/activate?language=${language}`, {
    method: 'POST',
  });
  await handleResponse(response);
}

// --- Quiz Questions ---

export async function listQuizQuestions(language: string = 'zh', category?: string, bankId?: string): Promise<{ questions: QuizQuestion[]; total: number }> {
  const params = new URLSearchParams({ language });
  if (bankId) params.set('bank_id', bankId);
  if (category) params.set('category', category);
  const response = await fetchWithApiKey(`${API_BASE}/jti/quiz-bank/questions/?${params}`);
  return handleResponse(response);
}

export async function getQuizQuestion(language: string, id: string, bankId?: string): Promise<QuizQuestion> {
  const params = new URLSearchParams({ language });
  if (bankId) params.set('bank_id', bankId);
  const response = await fetchWithApiKey(`${API_BASE}/jti/quiz-bank/questions/${encodeURIComponent(id)}?${params}`);
  return handleResponse(response);
}

export async function createQuizQuestion(language: string, question: QuizQuestion, bankId?: string): Promise<QuizQuestion> {
  const params = new URLSearchParams({ language });
  if (bankId) params.set('bank_id', bankId);
  const response = await fetchWithApiKey(`${API_BASE}/jti/quiz-bank/questions/?${params}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(question),
  });
  return handleResponse(response);
}

export async function updateQuizQuestion(language: string, id: string, data: Partial<QuizQuestion>, bankId?: string): Promise<QuizQuestion> {
  const params = new URLSearchParams({ language });
  if (bankId) params.set('bank_id', bankId);
  const response = await fetchWithApiKey(`${API_BASE}/jti/quiz-bank/questions/${encodeURIComponent(id)}?${params}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse(response);
}

export async function deleteQuizQuestion(language: string, id: string, bankId?: string): Promise<void> {
  const params = new URLSearchParams({ language });
  if (bankId) params.set('bank_id', bankId);
  const response = await fetchWithApiKey(`${API_BASE}/jti/quiz-bank/questions/${encodeURIComponent(id)}?${params}`, {
    method: 'DELETE',
  });
  await handleResponse(response);
}

// --- Quiz Metadata ---

export async function getQuizBankMetadata(language: string = 'zh', bankId?: string): Promise<QuizBankMetadata> {
  const params = new URLSearchParams({ language });
  if (bankId) params.set('bank_id', bankId);
  const response = await fetchWithApiKey(`${API_BASE}/jti/quiz-bank/metadata/?${params}`);
  return handleResponse(response);
}

export async function updateQuizBankMetadata(language: string, data: Partial<QuizBankMetadata>, bankId?: string): Promise<QuizBankMetadata> {
  const params = new URLSearchParams({ language });
  if (bankId) params.set('bank_id', bankId);
  const response = await fetchWithApiKey(`${API_BASE}/jti/quiz-bank/metadata/?${params}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse(response);
}

// --- Color Results ---

export async function listColorResults(language: string = 'zh'): Promise<{ results: ColorResult[]; total: number }> {
  const response = await fetchWithApiKey(`${API_BASE}/jti/quiz-bank/color-results/?language=${language}`);
  return handleResponse(response);
}

export async function updateColorResult(language: string, colorId: string, data: Partial<ColorResult>): Promise<ColorResult> {
  const response = await fetchWithApiKey(`${API_BASE}/jti/quiz-bank/color-results/${encodeURIComponent(colorId)}?language=${language}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse(response);
}

export async function exportColorResultsCsv(language: string): Promise<void> {
  const params = new URLSearchParams({ language });
  const response = await fetchWithApiKey(`${API_BASE}/jti/quiz-bank/color-results/export/?${params}`);
  if (!response.ok) throw new Error('Export failed');
  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `color_results_${language}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

// --- Quiz Stats ---

export async function getQuizBankStats(language: string = 'zh', bankId?: string): Promise<QuizBankStats> {
  const params = new URLSearchParams({ language });
  if (bankId) params.set('bank_id', bankId);
  const response = await fetchWithApiKey(`${API_BASE}/jti/quiz-bank/stats/?${params}`);
  return handleResponse(response);
}

// --- Import / Export ---

export async function importQuizBank(language: string, bankId: string, file: File, replace = false): Promise<{ count: number; message: string }> {
  const params = new URLSearchParams({ language, bank_id: bankId });
  if (replace) params.set('replace', 'true');
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetchWithApiKey(`${API_BASE}/jti/quiz-bank/import/?${params}`, {
    method: 'POST',
    body: formData,
  });
  return handleResponse(response);
}

export async function exportQuizBankCsv(language: string, bankId: string): Promise<void> {
  const params = new URLSearchParams({ language, bank_id: bankId });
  const response = await fetchWithApiKey(`${API_BASE}/jti/quiz-bank/export/?${params}`);
  if (!response.ok) throw new Error('Export failed');
  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `quiz_bank_${bankId}_${language}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
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
