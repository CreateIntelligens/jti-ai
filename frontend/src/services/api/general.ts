import type {
  Store,
  FileItem,
  ChatResponse,
  StartChatResponse,
  AppTarget,
  KnowledgeFile,
  KnowledgeFileContent,
} from '../../types';
import { API_BASE, fetchAsAdmin, fetchWithApiKey, fetchWithUserGeminiKey, handleResponse, STORAGE_KEYS, STORAGE_ACTIVE, normLang, buildUrl } from './base';
import { createQuizBankApi, type QuizBankApi } from './_shared/quizBank';
import { createQaKnowledgeApi } from './_shared/qaKnowledge';
import type { QaAdminCategory, QaCategory } from '../../config/qaTopics';
import type { QaImage } from './_shared/qaKnowledge';
import { normalizeImageId } from '../../utils/qaImage';

// ========== Stores & Files ==========

export async function fetchStores(app?: string): Promise<Store[]> {
  const response = await fetchWithUserGeminiKey(buildUrl(`${API_BASE}/stores`, { app }));
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

export async function uploadStoreFile(storeName: string, file: File): Promise<FileItem> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetchWithUserGeminiKey(`${API_BASE}/stores/${storeName}/files`, {
    method: 'POST',
    body: formData,
  });
  return handleResponse<FileItem>(response);
}

export async function deleteStoreFile(storeName: string, fileName: string): Promise<void> {
  const response = await fetchWithUserGeminiKey(
    `${API_BASE}/stores/${storeName}/files/${encodeURIComponent(fileName)}`,
    { method: 'DELETE' },
  );
  await handleResponse<void>(response);
}

export type StoreFileContent = KnowledgeFileContent;

export async function getStoreFileContent(
  storeName: string,
  fileName: string,
): Promise<StoreFileContent> {
  const response = await fetchWithUserGeminiKey(
    `${API_BASE}/stores/${storeName}/files/${encodeURIComponent(fileName)}/content`,
  );
  return handleResponse<StoreFileContent>(response);
}

export async function updateStoreFileContent(
  storeName: string,
  fileName: string,
  content: string,
): Promise<{ message: string; synced: boolean }> {
  const response = await fetchWithUserGeminiKey(
    `${API_BASE}/stores/${storeName}/files/${encodeURIComponent(fileName)}/content`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    },
  );
  return handleResponse<{ message: string; synced: boolean }>(response);
}

// ========== Knowledge Management ==========


// Admin knowledge route prefix per managed app. Each fixed app (jti/hciot/esg)
// has its own `/api/<app>-admin/knowledge` mount; an unmapped app would 404
// rather than silently fall back to another app's knowledge base.
function managedAdminPrefix(appTarget: AppTarget): string {
  return `${appTarget}-admin`;
}

function knowledgeFileUrl(filename: string, suffix: string, appTarget: AppTarget, language: string): string {
  const path = `${API_BASE}/${managedAdminPrefix(appTarget)}/knowledge/files/${encodeURIComponent(filename)}${suffix}`;
  return buildUrl(path, { language: normLang(language) });
}

export async function listManagedKnowledgeFiles(appTarget: AppTarget, language: string = 'zh'): Promise<{ files: KnowledgeFile[] }> {
  const url = buildUrl(`${API_BASE}/${managedAdminPrefix(appTarget)}/knowledge/files/`, { language: normLang(language) });
  const response = await fetchAsAdmin(url);
  return handleResponse<{ files: KnowledgeFile[] }>(response);
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
  const url = buildUrl(`${API_BASE}/${managedAdminPrefix(appTarget)}/knowledge/upload/`, { language: normLang(language) });
  const response = await fetchAsAdmin(url, {
    method: 'POST',
    body: formData,
  });
  return handleResponse<any>(response);
}

export async function deleteManagedKnowledgeFile(appTarget: AppTarget, fileName: string, language: string = 'zh'): Promise<any> {
  const response = await fetchAsAdmin(knowledgeFileUrl(fileName, '', appTarget, language), { method: 'DELETE' });
  return handleResponse<any>(response);
}

// ========== Models ==========

export interface ModelInfo {
  name: string;
  display_name: string;
  input_token_limit: number;
  output_token_limit: number;
}

export interface ModelsResponse {
  models: ModelInfo[];
  default_model: string;
}

export async function fetchModels(): Promise<ModelsResponse> {
  const response = await fetchWithUserGeminiKey(`${API_BASE}/models`);
  return handleResponse<ModelsResponse>(response);
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
  const data = await handleResponse<any>(response);
  return {
    session_id: data.session_id,
    opening_message: data.opening_message,
    prompt_applied: data.prompt_applied,
  };
}

export async function sendMessage(text: string, sessionId?: string, turnNumber?: number): Promise<ChatResponse> {
  const response = await fetchWithUserGeminiKey(`${API_BASE}/chat/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: text, session_id: sessionId, turn_number: turnNumber, model: getSelectedModel() }),
  });
  // 後端 general 已全線統一回 message;service 邊界映射成內部統一的 answer。
  const data = await handleResponse<any>(response);
  return {
    answer: data.message ?? '',
    turn_number: data.turn_number,
    citations: data.citations,
    image_id: data.image_id,
    tts_text: data.tts_text,
    tts_message_id: data.tts_message_id,
  };
}

// ========== Prompts ==========

export async function listPrompts(storeName: string): Promise<any> {
  const response = await fetchWithApiKey(`${API_BASE}/stores/${storeName}/prompts`);
  return handleResponse<any>(response);
}

type RuleSectionsByLanguage = Record<string, unknown> | null;

export async function createPrompt(
  storeName: string,
  name: string,
  content: string,
  contentEn?: string | null,
  responseRuleSections?: RuleSectionsByLanguage,
  maxResponseChars?: number | null,
): Promise<any> {
  const body = {
    name,
    content,
    ...(contentEn !== undefined && { content_en: contentEn }),
    ...(responseRuleSections !== undefined && { response_rule_sections: responseRuleSections }),
    ...(maxResponseChars !== undefined && { max_response_chars: maxResponseChars }),
  };
  const response = await fetchWithApiKey(`${API_BASE}/stores/${storeName}/prompts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return handleResponse<any>(response);
}

export async function updatePrompt(
  storeName: string,
  promptId: string,
  name?: string,
  content?: string,
  contentEn?: string | null,
  responseRuleSections?: RuleSectionsByLanguage,
  maxResponseChars?: number | null,
): Promise<any> {
  const body = {
    ...(name !== undefined && { name }),
    ...(content !== undefined && { content }),
    ...(contentEn !== undefined && { content_en: contentEn }),
    ...(responseRuleSections !== undefined && { response_rule_sections: responseRuleSections }),
    ...(maxResponseChars !== undefined && { max_response_chars: maxResponseChars }),
  };
  const response = await fetchWithApiKey(`${API_BASE}/stores/${storeName}/prompts/${promptId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
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
  const response = await fetchWithApiKey(
    buildUrl(`${API_BASE}/keys`, { store_name: storeName || undefined }),
  );
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

export async function revealApiKey(keyId: string): Promise<string> {
  const response = await fetchWithApiKey(`${API_BASE}/keys/${keyId}/reveal`);
  const data = await handleResponse<{ id: string; key: string }>(response);
  return data.key;
}

// ========== User Gemini API Keys (localStorage) ==========

interface SavedApiKey {
  name: string;
  key: string;
}

export function getSavedApiKeys(): SavedApiKey[] {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEYS) || '[]');
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
  const normalizedName = name.trim();
  const normalizedKey = key.trim();
  if (!normalizedName || !normalizedKey) return;

  const keys = getSavedApiKeys();
  const index = keys.findIndex(k => k.name === normalizedName);
  if (index >= 0) keys[index].key = normalizedKey;
  else keys.push({ name: normalizedName, key: normalizedKey });

  localStorage.setItem(STORAGE_KEYS, JSON.stringify(keys));
  setActiveApiKey(normalizedName);
}

export function deleteApiKey(name: string): void {
  const normalizedName = name.trim();
  const keys = getSavedApiKeys().filter(k => k.name !== normalizedName);
  localStorage.setItem(STORAGE_KEYS, JSON.stringify(keys));
  if (getActiveApiKeyName() === normalizedName) {
    setActiveApiKey('system');
  }
}

export function getActiveApiKeyName(): string {
  return (localStorage.getItem(STORAGE_ACTIVE) || 'system').trim() || 'system';
}

export function setActiveApiKey(name: string): void {
  localStorage.setItem(STORAGE_ACTIVE, name.trim() || 'system');
}

// ========== General Chat Conversations ==========

export interface ConversationHistoryPageParams {
  page?: number;
  pageSize?: number;
  dateFrom?: string;
  dateTo?: string;
}

export async function getGeneralConversations(
  storeName?: string,
  params: ConversationHistoryPageParams = {},
): Promise<any> {
  const response = await fetchWithUserGeminiKey(
    buildUrl(`${API_BASE}/chat/history`, {
      store_name: storeName || undefined,
      page: params.page,
      page_size: params.pageSize,
      date_from: params.dateFrom,
      date_to: params.dateTo,
    }),
  );
  return handleResponse<any>(response);
}

export async function getGeneralConversationDetail(sessionId: string): Promise<any> {
  const response = await fetchWithUserGeminiKey(`${API_BASE}/chat/history/${encodeURIComponent(sessionId)}`);
  return handleResponse<any>(response);
}

export async function deleteConversations(mode: 'jti' | 'hciot' | 'general', sessionIds: string[]): Promise<void> {
  const urlMap = {
    jti: `${API_BASE}/jti-admin/conversations`,
    hciot: `${API_BASE}/hciot-admin/conversations`,
    general: `${API_BASE}/chat/history`,
  };
  const url = urlMap[mode];
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

export interface ReindexStatusResponse {
  source_type: string;
  reindexing: boolean;
}

export async function getReindexStatus(sourceType: RagSourceType): Promise<ReindexStatusResponse> {
  const query = new URLSearchParams({ source_type: sourceType });
  const response = await fetchAsAdmin(API_BASE + '/admin/rag/status?' + query.toString(), {
    method: 'GET',
  });
  return handleResponse<ReindexStatusResponse>(response);
}

// ========== General Store Quiz APIs ==========

export interface StoreQuizConfig {
  quiz_enabled: boolean;
  quiz_start_keywords: string[];
  quiz_negative_keywords: string[];
  quiz_copy?: Record<string, any> | null;
}

export async function getStoreQuizConfig(storeName: string): Promise<StoreQuizConfig> {
  const response = await fetchWithApiKey(`${API_BASE}/stores/${storeName}/quiz-config`);
  return handleResponse<StoreQuizConfig>(response);
}

export async function updateStoreQuizConfig(storeName: string, config: StoreQuizConfig): Promise<void> {
  const response = await fetchWithApiKey(`${API_BASE}/stores/${storeName}/quiz-config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  await handleResponse<void>(response);
}

export function getGeneralQuizApi(storeName: string): QuizBankApi {
  return createQuizBankApi(`${API_BASE}/general/quiz-bank/${storeName}`);
}

export default reindexRag;

// ========== General per-store QA Knowledge Workspace ==========
// Mirrors the HCIoT knowledge/topics/images surface but keyed by store_name
// (carried in the `language` query param via an identity normalizer, since
// general is single-language and store_name must pass through unchanged).

const GENERAL_ADMIN_BASE = `${API_BASE}/general-admin`;
const GENERAL_JSON_HEADERS = { 'Content-Type': 'application/json' };

// Reuse the shared QA knowledge client; identity normalizer keeps store_name intact.
const generalQaKnowledgeApi = createQaKnowledgeApi(
  `${GENERAL_ADMIN_BASE}/knowledge`,
  (storeName) => storeName,
);

function generalJsonRequest(method: 'POST' | 'PUT' | 'DELETE', body?: unknown): RequestInit {
  return {
    method,
    headers: GENERAL_JSON_HEADERS,
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  };
}

// ----- Knowledge files / CSV (delegated to the shared client) -----

export function listGeneralKnowledgeFiles(storeName: string) {
  return generalQaKnowledgeApi.listKnowledgeFiles(storeName);
}

export function getGeneralKnowledgeFileContent(filename: string, storeName: string) {
  return generalQaKnowledgeApi.getKnowledgeFileContent(filename, storeName);
}

export function downloadGeneralKnowledgeFile(filename: string, storeName: string) {
  return generalQaKnowledgeApi.downloadKnowledgeFile(filename, storeName);
}

export function updateGeneralKnowledgeFileContent(filename: string, content: string, storeName: string) {
  return generalQaKnowledgeApi.updateKnowledgeFileContent(filename, content, storeName);
}

export function deleteGeneralKnowledgeFile(filename: string, storeName: string) {
  return generalQaKnowledgeApi.deleteKnowledgeFile(filename, storeName);
}

export function updateGeneralKnowledgeFileMetadata(
  filename: string,
  metadata: { topic_id?: string | null; category_label?: string | null; topic_label?: string | null },
  storeName: string,
) {
  return generalQaKnowledgeApi.updateKnowledgeFileMetadata(filename, metadata, storeName);
}

export function uploadGeneralKnowledgeFileWithTopic(opts: {
  storeName: string;
  file: File;
  categoryId?: string;
  topicId?: string;
  categoryLabel?: string;
  topicLabel?: string;
  hiddenQuestions?: string[];
}) {
  const { storeName, ...rest } = opts;
  return generalQaKnowledgeApi.uploadKnowledgeFileWithTopic({ ...rest, language: storeName });
}

export function getGeneralTopicMergedCsv(topicId: string, storeName: string) {
  return generalQaKnowledgeApi.getTopicMergedCsv(topicId, storeName);
}

export function saveGeneralTopicMergedCsv(
  topicId: string,
  payload: { files: Array<{ filename: string; content: string }>; delete_files?: string[]; hidden_questions?: string[] },
  storeName: string,
) {
  return generalQaKnowledgeApi.saveTopicMergedCsv(topicId, payload, storeName);
}

export function parseGeneralQaCsvText(text: string) {
  return generalQaKnowledgeApi.parseQaCsvText(text);
}

// ----- Topics (HCIoT-shaped category tree, keyed by store_name) -----

export async function listGeneralTopics(storeName: string): Promise<{ categories: QaCategory[] }> {
  const response = await fetchWithUserGeminiKey(
    `${API_BASE}/general/stores/${encodeURIComponent(storeName)}/topics`,
  );
  return handleResponse<{ categories: QaCategory[] }>(response);
}

async function generalAdminJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetchAsAdmin(`${GENERAL_ADMIN_BASE}${path}`, options);
  return handleResponse<T>(response);
}

export function listGeneralTopicsAdmin(storeName: string): Promise<{ categories: QaAdminCategory[] }> {
  // Unfiltered listing (includes hidden topics/questions) — served only under
  // the authed admin mount.
  return generalAdminJson<{ categories: QaAdminCategory[] }>(
    `/stores/${encodeURIComponent(storeName)}/topics/all`,
  );
}

export function createGeneralTopic(
  storeName: string,
  topicId: string,
  label: string,
  categoryLabel: string,
  questions: string[] = [],
): Promise<Record<string, unknown>> {
  return generalAdminJson<Record<string, unknown>>(
    `/stores/${encodeURIComponent(storeName)}/topics/`,
    generalJsonRequest('POST', {
      topic_id: topicId,
      labels: label,
      category_labels: categoryLabel,
      questions,
    }),
  );
}

export function updateGeneralTopic(
  storeName: string,
  topicId: string,
  data: { labels?: string; category_labels?: string; questions?: string[]; hidden_questions?: string[]; hidden?: boolean },
): Promise<Record<string, unknown>> {
  // topic_id may contain "/", so it is not URI-encoded (matches HCIoT).
  return generalAdminJson<Record<string, unknown>>(
    `/stores/${encodeURIComponent(storeName)}/topics/${topicId}`,
    generalJsonRequest('PUT', data),
  );
}

export function reorderGeneralTopics(storeName: string, topicIds: string[]): Promise<{ updated: number }> {
  return generalAdminJson<{ updated: number }>(
    `/stores/${encodeURIComponent(storeName)}/topics/reorder`,
    generalJsonRequest('PUT', { topic_ids: topicIds }),
  );
}

export function setGeneralCategoryHidden(
  storeName: string,
  categoryId: string,
  hidden: boolean,
): Promise<{ category_id: string; hidden: boolean }> {
  return generalAdminJson<{ category_id: string; hidden: boolean }>(
    `/stores/${encodeURIComponent(storeName)}/topics/categories/${encodeURIComponent(categoryId)}/visibility`,
    generalJsonRequest('PUT', { hidden }),
  );
}

// ----- Images (per-store) -----

// Browser-loadable URL for a general store's image (the QA workspace previews
// resolve image ids through config.resolveImageUrl; hciot uses its own scheme).
export function getGeneralImageUrl(storeName: string, imageId?: string): string | null {
  const normalized = normalizeImageId(imageId);
  if (!normalized) return null;
  return `${GENERAL_ADMIN_BASE}/stores/${encodeURIComponent(storeName)}/images/${encodeURIComponent(normalized)}`;
}

export function listGeneralImages(storeName: string): Promise<{ images: QaImage[] }> {
  return generalAdminJson<{ images: QaImage[] }>(
    `/stores/${encodeURIComponent(storeName)}/images`,
  );
}

export async function uploadGeneralImage(storeName: string, file: File, imageId?: string): Promise<QaImage> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('image_id', imageId || file.name.replace(/\.[^.]+$/, ''));
  return generalAdminJson<QaImage>(`/stores/${encodeURIComponent(storeName)}/images`, {
    method: 'POST',
    body: formData,
  });
}

export async function deleteGeneralImage(storeName: string, imageId: string): Promise<void> {
  await generalAdminJson<void>(
    `/stores/${encodeURIComponent(storeName)}/images/${encodeURIComponent(imageId)}`,
    { method: 'DELETE' },
  );
}

// ----- Per-store RAG reindex -----

export async function reindexGeneralStore(storeName: string): Promise<ReindexRagResponse> {
  return generalAdminJson<ReindexRagResponse>(
    `/knowledge/reindex?language=${encodeURIComponent(storeName)}`,
    { method: 'POST' },
  );
}

export async function getGeneralStoreReindexStatus(storeName: string): Promise<ReindexStatusResponse> {
  return generalAdminJson<ReindexStatusResponse>(
    `/knowledge/reindex-status?language=${encodeURIComponent(storeName)}`,
  );
}
