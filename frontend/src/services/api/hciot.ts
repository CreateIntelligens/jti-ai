import type { StartChatResponse, ChatResponse, Prompt, KnowledgeFile, KnowledgeFileContent } from '../../types';
import type { HciotCategory as HciotRuntimeCategory, HciotLanguage } from '../../config/hciotTopics';
import { API_BASE, fetchAsAdmin, fetchWithApiKey, handleResponse, normLang, buildUrl } from './base';

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
type QueryValue = string | null | undefined;

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

function appendOptionalFormValue(formData: FormData, key: string, value: string | undefined): void {
  if (value) {
    formData.append(key, value);
  }
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
  return fetchAdminJson<{ files: HciotKnowledgeFile[] }>('/knowledge/files/', undefined, {
    language: normLang(language),
  });
}

export async function getHciotKnowledgeFileContent(filename: string, language: string = 'zh'): Promise<HciotKnowledgeFileContent> {
  return fetchAdminJson<HciotKnowledgeFileContent>(
    `/knowledge/files/${encodeURIComponent(filename)}/content`,
    undefined,
    { language: normLang(language) },
  );
}

export function downloadHciotKnowledgeFile(filename: string, language: string = 'zh'): void {
  window.open(
    buildAdminUrl(`/knowledge/files/${encodeURIComponent(filename)}/download`, {
      language: normLang(language),
    }),
    '_blank',
  );
}

export async function updateHciotKnowledgeFileContent(
  filename: string,
  content: string,
  language: string = 'zh',
): Promise<{ message: string; synced: boolean; topic_synced: boolean }> {
  return fetchAdminJson<{ message: string; synced: boolean; topic_synced: boolean }>(
    `/knowledge/files/${encodeURIComponent(filename)}/content`,
    jsonRequest('PUT', { content }),
    { language: normLang(language) },
  );
}

export async function uploadHciotKnowledgeFile(
  language: string,
  file: File,
): Promise<HciotKnowledgeFile & { synced: boolean; topic_synced: boolean; uploaded_count?: number; uploaded_files?: string[] }> {
  const formData = new FormData();
  formData.append('file', file);
  return fetchAdminJson<HciotKnowledgeFile & { synced: boolean; topic_synced: boolean; uploaded_count?: number; uploaded_files?: string[] }>(
    '/knowledge/upload/',
    {
      method: 'POST',
      body: formData,
    },
    { language: normLang(language) },
  );
}

export async function deleteHciotKnowledgeFile(fileName: string, language: string = 'zh'): Promise<void> {
  await fetchAdminJson<void>(`/knowledge/files/${encodeURIComponent(fileName)}`, {
    method: 'DELETE',
  }, {
    language: normLang(language),
  });
}

export async function getHciotConversationDetail(sessionId: string): Promise<Record<string, unknown>> {
  return fetchAdminJson<Record<string, unknown>>('/conversations', undefined, {
    session_id: sessionId,
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
  return fetchAdminJson<HciotKnowledgeFile & { topic_synced: boolean }>(
    `/knowledge/files/${encodeURIComponent(filename)}/metadata`,
    jsonRequest('PUT', metadata),
    { language: normLang(language) },
  );
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
}

export interface HciotTopicCategory {
  id: string;
  order?: number;
  label: string;
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
  data: { labels?: string; category_labels?: string; questions?: string[]; hidden_questions?: string[] },
  language: HciotLanguage = 'zh',
): Promise<Record<string, unknown>> {
  // topic_id contains "/" so we can't use encodeURIComponent — pass raw
  return fetchAdminJson<Record<string, unknown>>(
    buildTopicAdminPath(language, topicId),
    jsonRequest('PUT', data),
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

export interface UploadWithTopicOptions {
  language: HciotLanguage;
  file: File;
  categoryId?: string;
  topicId?: string;
  // Single labels — implicitly in `language`. Backend only stores the label
  // for the doc's language partition.
  categoryLabel?: string;
  topicLabel?: string;
  skipTopic?: boolean;
  // Question texts the admin un-checked while typing the Q&A. Sent as a JSON
  // string Form field; the backend writes them to hidden_questions atomically
  // with the extracted questions.
  hiddenQuestions?: string[];
}

export async function uploadHciotKnowledgeFileWithTopic(
  opts: UploadWithTopicOptions,
): Promise<HciotKnowledgeFile & { synced: boolean; topic_synced: boolean; uploaded_count?: number; uploaded_files?: string[] }> {
  const formData = new FormData();
  formData.append('file', opts.file);
  // Backend still accepts category_id + topic_id as separate Form fields and merges them
  appendOptionalFormValue(formData, 'category_id', opts.categoryId);
  appendOptionalFormValue(formData, 'topic_id', opts.topicId);
  appendOptionalFormValue(formData, 'category_label', opts.categoryLabel);
  appendOptionalFormValue(formData, 'topic_label', opts.topicLabel);
  if (opts.skipTopic !== undefined) {
    formData.append('skip_topic', String(opts.skipTopic));
  }
  if (opts.hiddenQuestions !== undefined) {
    formData.append('hidden_questions', JSON.stringify(opts.hiddenQuestions));
  }

  return fetchAdminJson<HciotKnowledgeFile & { synced: boolean; topic_synced: boolean; uploaded_count?: number; uploaded_files?: string[] }>(
    '/knowledge/upload/',
    { method: 'POST', body: formData },
    { language: normLang(opts.language) },
  );
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

export interface HciotMergedCsvRow {
  index: string;
  q: string;
  a: string;
  img: string;
  url?: string;
  source_file?: string;
}

export interface HciotMergedCsvResponse {
  rows: HciotMergedCsvRow[];
  source_files: string[];
}

export async function getHciotTopicMergedCsv(topicId: string, language: HciotLanguage = 'zh'): Promise<HciotMergedCsvResponse> {
  return fetchAdminJson<HciotMergedCsvResponse>('/knowledge/topic-csv-merged', undefined, {
    topic_id: topicId,
    language: normLang(language),
  });
}
