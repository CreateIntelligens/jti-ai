import type { StartChatResponse, ChatResponse } from '../../types';
import { API_BASE, fetchAsAdmin, fetchWithApiKey, handleResponse } from './base';

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

export interface HciotPrompt {
  id: string;
  name: string;
  content: string;
  created_at: string;
  updated_at: string;
  is_default?: boolean;
  readonly?: boolean;
  is_active?: boolean;
}

export interface HciotPromptListResponse {
  prompts: HciotPrompt[];
  active_prompt_id: string | null;
  max_custom_prompts?: number;
}

export interface HciotKnowledgeFile {
  name: string;
  display_name?: string;
  content_type?: string;
  size?: number;
  created_at?: string;
  editable?: boolean;
  topic_id?: string | null;
  category_label_zh?: string | null;
  category_label_en?: string | null;
  topic_label_zh?: string | null;
  topic_label_en?: string | null;
}

export interface HciotKnowledgeFileContent {
  filename: string;
  content: string | null;
  editable?: boolean;
  size?: number;
  message?: string;
}

export interface HciotLabels {
  zh: string;
  en: string;
}

export interface HciotTopicQuestions {
  zh: string[];
  en: string[];
}

const HCIOT_ADMIN_BASE = `${API_BASE}/hciot-admin`;
const HCIOT_API_BASE = `${API_BASE}/hciot`;
const JSON_HEADERS = { 'Content-Type': 'application/json' };
type QueryValue = string | null | undefined;

function normLang(language: string): string {
  return language.toLowerCase().startsWith('en') ? 'en' : 'zh';
}

function buildQuery(params: Record<string, QueryValue>): string {
  const query = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value) {
      query.set(key, value);
    }
  });

  return query.toString();
}

function appendQuery(path: string, params: Record<string, QueryValue>): string {
  const query = buildQuery(params);
  return query ? `${path}?${query}` : path;
}

function buildAdminUrl(path: string, params?: Record<string, QueryValue>): string {
  return `${HCIOT_ADMIN_BASE}${appendQuery(path, params || {})}`;
}

function buildApiUrl(path: string, params?: Record<string, QueryValue>): string {
  return `${HCIOT_API_BASE}${appendQuery(path, params || {})}`;
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

async function fetchApiJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetchWithApiKey(buildApiUrl(path), options);
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
  const payload: Record<string, unknown> = { message: text, session_id: sessionId };
  if (turnNumber !== undefined) payload.turn_number = turnNumber;
  if (ttsCharacter) payload.tts_character = ttsCharacter;
  const response = await fetchWithApiKey('/api/hciot/chat/message', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await handleResponse<Record<string, unknown>>(response);
  return {
    answer: (data.message ?? data.answer ?? '') as string,
    turn_number: data.turn_number as number | undefined,
    citations: data.citations as Array<{ title: string; uri: string }> | undefined,
    image_id: data.image_id as string | undefined,
    tts_text: data.tts_text as string | undefined,
    tts_message_id: data.tts_message_id as string | undefined,
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
    category_label_zh?: string | null;
    category_label_en?: string | null;
    topic_label_zh?: string | null;
    topic_label_en?: string | null;
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

export interface HciotTopicCategory {
  id: string;
  labels: HciotLabels;
  topics: Array<{
    id: string;
    order?: number;
    labels: HciotLabels;
    category_labels?: HciotLabels;
    questions: HciotTopicQuestions;
  }>;
}

export async function listHciotTopicsAdmin(): Promise<{ categories: HciotTopicCategory[] }> {
  return fetchApiJson<{ categories: HciotTopicCategory[] }>('/topics');
}

export async function updateHciotTopic(
  topicId: string,
  data: { labels?: HciotLabels; category_labels?: HciotLabels; questions?: HciotTopicQuestions },
): Promise<Record<string, unknown>> {
  // topic_id contains "/" so we can't use encodeURIComponent — pass raw
  return fetchAdminJson<Record<string, unknown>>(
    `/topics/${topicId}`,
    jsonRequest('PUT', data),
  );
}

export async function deleteHciotTopic(topicId: string): Promise<void> {
  await fetchAdminJson<void>(`/topics/${topicId}`, { method: 'DELETE' });
}

export async function createHciotTopic(
  topicId: string,
  labels: HciotLabels,
  categoryLabels: HciotLabels,
  questions: HciotTopicQuestions = { zh: [], en: [] },
): Promise<Record<string, unknown>> {
  return fetchAdminJson<Record<string, unknown>>('/topics/', jsonRequest('POST', {
    topic_id: topicId,
    labels,
    category_labels: categoryLabels,
    questions,
  }));
}

export interface UploadWithTopicOptions {
  language: string;
  file: File;
  categoryId?: string;
  topicId?: string;
  categoryLabelZh?: string;
  categoryLabelEn?: string;
  topicLabelZh?: string;
  topicLabelEn?: string;
}

export async function uploadHciotKnowledgeFileWithTopic(
  opts: UploadWithTopicOptions,
): Promise<HciotKnowledgeFile & { synced: boolean; topic_synced: boolean; uploaded_count?: number; uploaded_files?: string[] }> {
  const formData = new FormData();
  formData.append('file', opts.file);
  // Backend still accepts category_id + topic_id as separate Form fields and merges them
  appendOptionalFormValue(formData, 'category_id', opts.categoryId);
  appendOptionalFormValue(formData, 'topic_id', opts.topicId);
  appendOptionalFormValue(formData, 'category_label_zh', opts.categoryLabelZh);
  appendOptionalFormValue(formData, 'category_label_en', opts.categoryLabelEn);
  appendOptionalFormValue(formData, 'topic_label_zh', opts.topicLabelZh);
  appendOptionalFormValue(formData, 'topic_label_en', opts.topicLabelEn);

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
  source_file?: string;
}

export interface HciotMergedCsvResponse {
  rows: HciotMergedCsvRow[];
  source_files: string[];
}

export async function getHciotTopicMergedCsv(topicId: string, language: string = 'zh'): Promise<HciotMergedCsvResponse> {
  return fetchAdminJson<HciotMergedCsvResponse>('/knowledge/topic-csv-merged', undefined, {
    topic_id: topicId,
    language: normLang(language),
  });
}
