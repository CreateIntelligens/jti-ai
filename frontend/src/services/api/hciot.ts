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
  size?: number;
  created_at?: string;
}

export interface HciotKnowledgeFileContent {
  filename: string;
  content: string;
}

const HCIOT_ADMIN_BASE = `${API_BASE}/hciot-admin`;

function normLang(language: string): string {
  return language.toLowerCase().startsWith('en') ? 'en' : 'zh';
}

export async function hciotStartChat(language: string, previousSessionId?: string | null): Promise<StartChatResponse> {
  const response = await fetchWithApiKey('/api/hciot/chat/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ language, previous_session_id: previousSessionId || undefined }),
  });
  return handleResponse<StartChatResponse>(response);
}

export async function hciotSendMessage(text: string, sessionId: string, turnNumber?: number): Promise<ChatResponse> {
  const payload: Record<string, unknown> = { message: text, session_id: sessionId };
  if (turnNumber !== undefined) payload.turn_number = turnNumber;
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
  };
}

export async function listHciotPrompts(language: string = 'zh'): Promise<HciotPromptListResponse> {
  const response = await fetchAsAdmin(`${HCIOT_ADMIN_BASE}/prompts/?language=${normLang(language)}`);
  return handleResponse<HciotPromptListResponse>(response);
}

export async function createHciotPrompt(name: string, content: string, language: string = 'zh'): Promise<HciotPrompt> {
  const response = await fetchAsAdmin(`${HCIOT_ADMIN_BASE}/prompts/?language=${normLang(language)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, content }),
  });
  return handleResponse<HciotPrompt>(response);
}

export async function updateHciotPrompt(promptId: string, name?: string, content?: string, language: string = 'zh'): Promise<HciotPrompt> {
  const response = await fetchAsAdmin(`${HCIOT_ADMIN_BASE}/prompts/${promptId}?language=${normLang(language)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, content }),
  });
  return handleResponse<HciotPrompt>(response);
}

export async function deleteHciotPrompt(promptId: string, language: string = 'zh'): Promise<void> {
  const response = await fetchAsAdmin(`${HCIOT_ADMIN_BASE}/prompts/${promptId}?language=${normLang(language)}`, {
    method: 'DELETE',
  });
  await handleResponse<void>(response);
}

export async function setActiveHciotPrompt(promptId: string | null, language: string = 'zh'): Promise<void> {
  const response = await fetchAsAdmin(`${HCIOT_ADMIN_BASE}/prompts/active?language=${normLang(language)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt_id: promptId }),
  });
  await handleResponse<void>(response);
}

export async function cloneDefaultHciotPrompt(language: string = 'zh'): Promise<HciotPrompt> {
  const response = await fetchAsAdmin(`${HCIOT_ADMIN_BASE}/prompts/clone?language=${normLang(language)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  return handleResponse<HciotPrompt>(response);
}

export async function getHciotRuntimeSettings(promptId?: string, language: string = 'zh'): Promise<HciotRuntimeSettingsResponse> {
  const query = new URLSearchParams({ language: normLang(language) });
  if (promptId) query.set('prompt_id', promptId);
  const response = await fetchAsAdmin(`${HCIOT_ADMIN_BASE}/prompts/runtime-settings?${query}`);
  return handleResponse<HciotRuntimeSettingsResponse>(response);
}

export async function updateHciotRuntimeSettings(
  settings: HciotRuntimeSettings,
  promptId?: string,
  language: string = 'zh',
): Promise<{ settings: HciotRuntimeSettings; message: string; prompt_id?: string }> {
  const payload = promptId ? { ...settings, prompt_id: promptId } : settings;
  const response = await fetchAsAdmin(`${HCIOT_ADMIN_BASE}/prompts/runtime-settings?language=${normLang(language)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse(response);
}

export async function listHciotKnowledgeFiles(language: string = 'zh'): Promise<{ files: HciotKnowledgeFile[] }> {
  const response = await fetchAsAdmin(`${HCIOT_ADMIN_BASE}/knowledge/files/?language=${normLang(language)}`);
  return handleResponse<{ files: HciotKnowledgeFile[] }>(response);
}

export async function getHciotKnowledgeFileContent(filename: string, language: string = 'zh'): Promise<HciotKnowledgeFileContent> {
  const response = await fetchAsAdmin(`${HCIOT_ADMIN_BASE}/knowledge/files/${encodeURIComponent(filename)}/content?language=${normLang(language)}`);
  return handleResponse<HciotKnowledgeFileContent>(response);
}

export function downloadHciotKnowledgeFile(filename: string, language: string = 'zh'): void {
  const params = new URLSearchParams({ language: normLang(language) });
  window.open(`${HCIOT_ADMIN_BASE}/knowledge/files/${encodeURIComponent(filename)}/download?${params}`, '_blank');
}

export async function updateHciotKnowledgeFileContent(filename: string, content: string, language: string = 'zh'): Promise<HciotKnowledgeFileContent> {
  const response = await fetchAsAdmin(`${HCIOT_ADMIN_BASE}/knowledge/files/${encodeURIComponent(filename)}/content?language=${normLang(language)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });
  return handleResponse<HciotKnowledgeFileContent>(response);
}

export async function uploadHciotKnowledgeFile(language: string, file: File): Promise<{ filename: string; message: string }> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetchAsAdmin(`${HCIOT_ADMIN_BASE}/knowledge/upload/?language=${normLang(language)}`, {
    method: 'POST',
    body: formData,
  });
  return handleResponse<{ filename: string; message: string }>(response);
}

export async function deleteHciotKnowledgeFile(fileName: string, language: string = 'zh'): Promise<void> {
  const response = await fetchAsAdmin(`${HCIOT_ADMIN_BASE}/knowledge/files/${encodeURIComponent(fileName)}?language=${normLang(language)}`, {
    method: 'DELETE',
  });
  await handleResponse<void>(response);
}

export async function getHciotConversationDetail(sessionId: string): Promise<Record<string, unknown>> {
  const response = await fetchAsAdmin(`${HCIOT_ADMIN_BASE}/conversations?session_id=${encodeURIComponent(sessionId)}`);
  return handleResponse<Record<string, unknown>>(response);
}
