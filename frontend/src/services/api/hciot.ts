import type { StartChatResponse, ChatResponse, Prompt, KnowledgeFile, KnowledgeFileContent } from '../../types';
import type { HciotCategory as HciotRuntimeCategory, HciotLanguage } from '../../config/hciotTopics';
import { API_BASE, fetchAsAdmin, fetchWithApiKey, handleResponse, normLang, buildUrl } from './base';
import {
  createQaKnowledgeApi,
  type QaExtractJobResponse as SharedQaExtractJobResponse,
  type QaImportResponse as SharedQaImportResponse,
  type QaKnowledgeUploadWithTopicOptions,
  type QaMergedCsvResponse,
  type QaMergedCsvRow,
  type QaPair,
} from './_shared/qaKnowledge';

export interface HciotRuntimeSettings {
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
    zh: { title: string; description: string };
    en: { title: string; description: string };
  };
  max_response_chars: number;
}

export interface HciotRuntimeSettingsResponse {
  prompt_id?: string;
  settings: HciotRuntimeSettings;
}

export type HciotPrompt = Prompt;
export type HciotKnowledgeFile = KnowledgeFile;
export type HciotKnowledgeFileContent = KnowledgeFileContent;

export interface HciotPromptListResponse {
  prompts: Prompt[];
  active_prompt_id: string | null;
  max_custom_prompts?: number;
}

const HCIOT_ADMIN_BASE = `${API_BASE}/hciot-admin`;
const HCIOT_API_BASE = `${API_BASE}/hciot`;
const JSON_HEADERS = { 'Content-Type': 'application/json' };
const hciotQaKnowledgeApi = createQaKnowledgeApi(`${HCIOT_ADMIN_BASE}/knowledge`);
type QueryValue = string | number | boolean | null | undefined;

function buildAdminUrl(path: string, params?: Record<string, string | number | boolean | null | undefined>): string {
  return buildUrl(`${HCIOT_ADMIN_BASE}${path}`, params);
}

function buildApiUrl(path: string, params?: Record<string, string | number | boolean | null | undefined>): string {
  return buildUrl(`${HCIOT_API_BASE}${path}`, params);
}

function jsonRequest(method: 'POST' | 'PUT', body: unknown): RequestInit {
  return {
    method,
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  };
}

async function fetchAdminJson<T>(
  path: string,
  options?: RequestInit,
  params?: Record<string, QueryValue>,
): Promise<T> {
  const response = await fetchAsAdmin(buildAdminUrl(path, params), options);
  return handleResponse<T>(response);
}

async function fetchApiJson<T>(
  path: string,
  options?: RequestInit,
  params?: Record<string, QueryValue>,
): Promise<T> {
  const response = await fetchWithApiKey(buildApiUrl(path, params), options);
  return handleResponse<T>(response);
}

export async function getHciotTtsCharacters(): Promise<{ characters: string[] }> {
  return fetchApiJson<{ characters: string[] }>('/tts/characters');
}

export async function hciotStartChat(language: string, previousSessionId?: string | null): Promise<StartChatResponse> {
  const response = await fetchWithApiKey('/api/hciot/chat/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ language, previous_session_id: previousSessionId || undefined }),
  });
  return handleResponse<StartChatResponse>(response);
}

export async function hciotSendMessage(
  text: string,
  sessionId: string,
  turnNumber?: number,
  ttsCharacter?: string,
): Promise<ChatResponse> {
  const response = await fetchWithApiKey('/api/hciot/chat/message', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: text, session_id: sessionId, turn_number: turnNumber, tts_character: ttsCharacter }),
  });
  const data = await handleResponse<any>(response);
  return {
    answer: data.message ?? data.answer ?? '',
    turn_number: data.turn_number,
    citations: data.citations,
    image_id: data.image_id,
    tts_text: data.tts_text,
    tts_message_id: data.tts_message_id,
  };
}

export async function listHciotPrompts(language: string = 'zh'): Promise<HciotPromptListResponse> {
  return fetchAdminJson<HciotPromptListResponse>('/prompts/', undefined, {
    language: normLang(language),
  });
}

export async function createHciotPrompt(name: string, content: string, language: string = 'zh'): Promise<HciotPrompt> {
  return fetchAdminJson<HciotPrompt>('/prompts/', jsonRequest('POST', { name, content }), {
    language: normLang(language),
  });
}

export async function updateHciotPrompt(promptId: string, name?: string, content?: string, language: string = 'zh'): Promise<HciotPrompt> {
  return fetchAdminJson<HciotPrompt>(`/prompts/${promptId}`, jsonRequest('PUT', { name, content }), {
    language: normLang(language),
  });
}

export async function deleteHciotPrompt(promptId: string, language: string = 'zh'): Promise<void> {
  await fetchAdminJson<void>(`/prompts/${promptId}`, {
    method: 'DELETE',
  }, {
    language: normLang(language),
  });
}

export async function setActiveHciotPrompt(promptId: string | null, language: string = 'zh'): Promise<void> {
  await fetchAdminJson<void>('/prompts/active', jsonRequest('POST', { prompt_id: promptId }), {
    language: normLang(language),
  });
}

export async function cloneDefaultHciotPrompt(language: string = 'zh'): Promise<HciotPrompt> {
  return fetchAdminJson<HciotPrompt>('/prompts/clone', {
    method: 'POST',
  }, {
    language: normLang(language),
  });
}

export async function getHciotRuntimeSettings(promptId?: string, language: string = 'zh'): Promise<HciotRuntimeSettingsResponse> {
  return fetchAdminJson<HciotRuntimeSettingsResponse>('/prompts/runtime-settings', undefined, {
    language: normLang(language),
    prompt_id: promptId,
  });
}

export async function updateHciotRuntimeSettings(
  settings: HciotRuntimeSettings,
  promptId?: string,
  language: string = 'zh',
): Promise<{ settings: HciotRuntimeSettings; message: string; prompt_id?: string }> {
  const payload = promptId ? { ...settings, prompt_id: promptId } : settings;
  return fetchAdminJson<{ settings: HciotRuntimeSettings; message: string; prompt_id?: string }>(
    '/prompts/runtime-settings',
    jsonRequest('POST', payload),
    { language: normLang(language) },
  );
}

export async function listHciotKnowledgeFiles(language: string = 'zh'): Promise<{ files: HciotKnowledgeFile[] }> {
  return hciotQaKnowledgeApi.listKnowledgeFiles(language);
}

export async function getHciotKnowledgeFileContent(filename: string, language: string = 'zh'): Promise<HciotKnowledgeFileContent> {
  return hciotQaKnowledgeApi.getKnowledgeFileContent(filename, language);
}

export function downloadHciotKnowledgeFile(filename: string, language: string = 'zh'): void {
  hciotQaKnowledgeApi.downloadKnowledgeFile(filename, language);
}

export async function updateHciotKnowledgeFileContent(
  filename: string,
  content: string,
  language: string = 'zh',
): Promise<{ message: string; synced: boolean; topic_synced: boolean }> {
  return hciotQaKnowledgeApi.updateKnowledgeFileContent(filename, content, language);
}

export async function deleteHciotKnowledgeFile(fileName: string, language: string = 'zh'): Promise<void> {
  await hciotQaKnowledgeApi.deleteKnowledgeFile(fileName, language);
}

export async function getHciotConversationDetail(sessionId: string): Promise<Record<string, unknown>> {
  return fetchAdminJson<Record<string, unknown>>('/conversations', undefined, {
    session_id: sessionId,
  });
}

export async function getHciotConversations(params: {
  page?: number;
  pageSize?: number;
  dateFrom?: string;
  dateTo?: string;
} = {}): Promise<Record<string, unknown>> {
  return fetchAdminJson<Record<string, unknown>>('/conversations', undefined, {
    page: params.page,
    page_size: params.pageSize,
    date_from: params.dateFrom,
    date_to: params.dateTo,
  });
}

export async function updateHciotKnowledgeFileMetadata(
  filename: string,
  metadata: {
    topic_id?: string | null;
    category_label?: string | null;
    topic_label?: string | null;
  },
  language: string = 'zh',
): Promise<HciotKnowledgeFile & { topic_synced: boolean }> {
  return hciotQaKnowledgeApi.updateKnowledgeFileMetadata(filename, metadata, language);
}

// ========== Topic Admin ==========

// Topics are single-language end-to-end: each request/response carries the
// label for one language only. The category tree shape is identical for the
// public chat area and the admin UI.
export interface HciotTopic {
  id: string;
  order?: number;
  label: string;
  questions: string[];
  hidden_questions?: string[];
  hidden?: boolean;
}

export interface HciotTopicCategory {
  id: string;
  order?: number;
  label: string;
  hidden?: boolean;
  topics: HciotTopic[];
}

export async function listHciotTopics(language: HciotLanguage = 'zh'): Promise<{ categories: HciotRuntimeCategory[] }> {
  const lang = normLang(language);
  return fetchApiJson<{ categories: HciotRuntimeCategory[] }>(`/topics/${lang}`);
}

export async function listHciotTopicsAdmin(language: HciotLanguage = 'zh'): Promise<{ categories: HciotTopicCategory[] }> {
  const lang = normLang(language);
  return fetchApiJson<{ categories: HciotTopicCategory[] }>(`/topics/${lang}/all`);
}

function buildTopicAdminPath(language: HciotLanguage, topicId?: string): string {
  const basePath = `/topics/${normLang(language)}`;
  return topicId ? `${basePath}/${topicId}` : `${basePath}/`;
}

export async function updateHciotTopic(
  topicId: string,
  data: {
    labels?: string;
    category_labels?: string;
    questions?: string[];
    hidden_questions?: string[];
    hidden?: boolean;
  },
  language: HciotLanguage = 'zh',
): Promise<Record<string, unknown>> {
  // topic_id contains "/" so we can't use encodeURIComponent — pass raw
  return fetchAdminJson<Record<string, unknown>>(
    buildTopicAdminPath(language, topicId),
    jsonRequest('PUT', data),
  );
}

export async function setHciotCategoryHidden(
  categoryId: string,
  hidden: boolean,
  language: HciotLanguage = 'zh',
): Promise<{ category_id: string; hidden: boolean }> {
  return fetchAdminJson<{ category_id: string; hidden: boolean }>(
    `/topics/categories/${normLang(language)}/${encodeURIComponent(categoryId)}/visibility`,
    jsonRequest('PUT', { hidden }),
  );
}

export async function deleteHciotTopic(topicId: string, language: HciotLanguage = 'zh'): Promise<void> {
  await fetchAdminJson<void>(buildTopicAdminPath(language, topicId), { method: 'DELETE' });
}

export async function createHciotTopic(
  topicId: string,
  label: string,
  categoryLabel: string,
  questions: string[] = [],
  language: HciotLanguage = 'zh',
): Promise<Record<string, unknown>> {
  const payload = {
    topic_id: topicId,
    labels: label,
    category_labels: categoryLabel,
    questions,
  };
  return fetchAdminJson<Record<string, unknown>>(buildTopicAdminPath(language), jsonRequest('POST', payload));
}

/**
 * Persist a new topic ordering. `topicIds` is the full flat list of topic ids
 * in the desired display order; the backend rewrites each topic's `order`.
 */
export async function reorderHciotTopics(
  topicIds: string[],
  language: HciotLanguage = 'zh',
): Promise<{ updated: number }> {
  return fetchAdminJson<{ updated: number }>(
    buildTopicAdminPath(language, 'reorder'),
    jsonRequest('PUT', { topic_ids: topicIds }),
  );
}

export interface UploadWithTopicOptions extends QaKnowledgeUploadWithTopicOptions {
  language: HciotLanguage;
}

export async function uploadHciotKnowledgeFileWithTopic(
  opts: UploadWithTopicOptions,
): Promise<HciotKnowledgeFile & { synced: boolean; topic_synced: boolean; uploaded_count?: number; uploaded_files?: string[] }> {
  return hciotQaKnowledgeApi.uploadKnowledgeFileWithTopic(opts);
}

// ========== Image Admin ==========

export interface HciotImage {
  image_id: string;
  size_bytes: number;
  url: string;
  reference_count?: number;
  is_referenced?: boolean;
}

export async function listHciotImages(): Promise<{ images: HciotImage[] }> {
  return fetchAdminJson<{ images: HciotImage[] }>('/images/');
}

export async function uploadHciotImage(file: File, imageId?: string): Promise<HciotImage> {
  const formData = new FormData();
  formData.append('file', file);
  if (imageId) {
    formData.append('image_id', imageId);
  }
  return fetchAdminJson<HciotImage>('/images/upload', {
    method: 'POST',
    body: formData,
  });
}

export async function deleteHciotImage(imageId: string): Promise<void> {
  await fetchAdminJson<void>(`/images/${encodeURIComponent(imageId)}`, {
    method: 'DELETE',
  });
}

export async function deleteUnusedHciotImages(): Promise<{ deleted_count: number; deleted_image_ids: string[] }> {
  return fetchAdminJson<{ deleted_count: number; deleted_image_ids: string[] }>('/images/cleanup-unused', {
    method: 'DELETE',
  });
}

// ========== Merged CSV ==========

export type HciotMergedCsvRow = QaMergedCsvRow;

export type HciotMergedCsvResponse = QaMergedCsvResponse;

export async function getHciotTopicMergedCsv(topicId: string, language: HciotLanguage = 'zh'): Promise<HciotMergedCsvResponse> {
  return hciotQaKnowledgeApi.getTopicMergedCsv(topicId, language);
}

// ========== Document to Q&A Extraction API ==========

export type HciotQaPair = QaPair;

export type QaExtractJobResponse = SharedQaExtractJobResponse;

export type QaImportResponse = SharedQaImportResponse;

export async function createQaExtractJob(
  language: string,
  source: { file: File } | { text: string },
  categoryId: string,
  topicId: string,
  categoryLabel: string,
  topicLabel: string,
): Promise<{ job_id: string; status: string }> {
  return hciotQaKnowledgeApi.createQaExtractJob(
    language,
    source,
    categoryId,
    topicId,
    categoryLabel,
    topicLabel,
  );
}

export async function parseQaCsvText(text: string): Promise<{ parsed: boolean; qa_pairs: HciotQaPair[] }> {
  return hciotQaKnowledgeApi.parseQaCsvText(text);
}

export async function getQaExtractJob(jobId: string): Promise<QaExtractJobResponse> {
  return hciotQaKnowledgeApi.getQaExtractJob(jobId);
}

export async function importQaExtractJob(
  jobId: string,
  language: string,
  qaPairs: HciotQaPair[],
  hiddenQuestions?: string[],
): Promise<QaImportResponse> {
  return hciotQaKnowledgeApi.importQaExtractJob(jobId, language, qaPairs, hiddenQuestions);
}
