import { API_BASE, fetchAsAdmin, handleResponse, normLang, buildUrl } from './base';
import { createQuizBankApi } from './_shared/quizBank';

// ========== JTI Types ==========

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
    zh: { title: string; description: string };
    en: { title: string; description: string };
  };
  max_response_chars: number;
  tts_character?: string;
}

export interface JtiRuntimeSettingsResponse {
  prompt_id?: string;
  settings: JtiRuntimeSettings;
}


const JTI_ADMIN_BASE = `${API_BASE}/jti-admin`;

function jtiUrl(path: string, language: string = 'zh', extraParams?: Record<string, string | number | boolean>): string {
  return buildUrl(`${JTI_ADMIN_BASE}${path}`, { language: normLang(language), ...extraParams });
}

type ApiMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
type ApiParams = Record<string, string | number | boolean>;

/** Internal helper for common JSON API calls */
async function apiCall<T = any>(
  method: ApiMethod,
  path: string,
  language: string,
  body?: unknown,
  params?: ApiParams,
): Promise<T> {
  const options: RequestInit = { method };
  if (body !== undefined) {
    options.headers = { 'Content-Type': 'application/json' };
    options.body = JSON.stringify(body);
  }
  const response = await fetchAsAdmin(jtiUrl(path, language, params), options);
  return handleResponse<T>(response);
}

// ========== JTI Prompt Management ==========

export async function listJtiPrompts(language: string = 'zh'): Promise<any> {
  return apiCall('GET', '/prompts/', language);
}

export async function createJtiPrompt(name: string, content: string, language: string = 'zh'): Promise<any> {
  return apiCall('POST', '/prompts/', language, { name, content });
}

export async function updateJtiPrompt(promptId: string, name?: string, content?: string, language: string = 'zh'): Promise<any> {
  return apiCall('PUT', `/prompts/${promptId}`, language, { name, content });
}

export async function deleteJtiPrompt(promptId: string, language: string = 'zh'): Promise<void> {
  return apiCall('DELETE', `/prompts/${promptId}`, language);
}

export async function setActiveJtiPrompt(promptId: string | null, language: string = 'zh'): Promise<void> {
  return apiCall('POST', '/prompts/active', language, { prompt_id: promptId });
}

export async function cloneDefaultJtiPrompt(language: string = 'zh'): Promise<any> {
  return apiCall('POST', '/prompts/clone', language);
}

export async function getJtiRuntimeSettings(promptId?: string, language: string = 'zh'): Promise<JtiRuntimeSettingsResponse> {
  return apiCall('GET', '/prompts/runtime-settings', language, undefined, promptId ? { prompt_id: promptId } : {});
}

export async function getJtiConversationDetail(sessionId: string): Promise<Record<string, unknown>> {
  const response = await fetchAsAdmin(buildUrl(`${JTI_ADMIN_BASE}/conversations`, { session_id: sessionId }));
  return handleResponse<Record<string, unknown>>(response);
}

export async function getJtiConversations(params: {
  page?: number;
  pageSize?: number;
  dateFrom?: string;
  dateTo?: string;
} = {}): Promise<Record<string, unknown>> {
  const response = await fetchAsAdmin(
    buildUrl(`${JTI_ADMIN_BASE}/conversations`, {
      page: params.page,
      page_size: params.pageSize,
      date_from: params.dateFrom,
      date_to: params.dateTo,
    }),
  );
  return handleResponse<Record<string, unknown>>(response);
}

export async function updateJtiRuntimeSettings(
  settings: JtiRuntimeSettings,
  promptId?: string,
  language: string = 'zh',
): Promise<{ settings: JtiRuntimeSettings; message: string; prompt_id?: string }> {
  return apiCall('POST', '/prompts/runtime-settings', language, { ...settings, prompt_id: promptId });
}

// ========== JTI 知識庫管理 ==========

export async function listJtiKnowledgeFiles(language: string = 'zh'): Promise<any> {
  return apiCall('GET', '/knowledge/files/', language);
}

export async function getJtiKnowledgeFileContent(filename: string, language: string = 'zh'): Promise<any> {
  return apiCall('GET', `/knowledge/files/${encodeURIComponent(filename)}/content`, language);
}

export async function downloadJtiKnowledgeFile(filename: string, language: string = 'zh'): Promise<void> {
  window.open(jtiUrl(`/knowledge/files/${encodeURIComponent(filename)}/download`, language), '_blank');
}

export async function updateJtiKnowledgeFileContent(filename: string, content: string, language: string = 'zh'): Promise<any> {
  return apiCall('PUT', `/knowledge/files/${encodeURIComponent(filename)}/content`, language, { content });
}

export async function uploadJtiKnowledgeFile(language: string, file: File): Promise<any> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetchAsAdmin(jtiUrl('/knowledge/upload/', language), { method: 'POST', body: formData });
  return handleResponse<any>(response);
}

export async function deleteJtiKnowledgeFile(fileName: string, language: string = 'zh'): Promise<any> {
  return apiCall('DELETE', `/knowledge/files/${encodeURIComponent(fileName)}`, language);
}

// ========== JTI 題庫管理 ==========

import type {
  QuizQuestionOption,
  QuizQuestion,
  QuizBank,
  QuizBankMetadata,
  QuizResult,
  QuizSet,
  QuizBankStats,
  QuizBankApi,
} from './_shared/quizBank';

export type {
  QuizQuestionOption,
  QuizQuestion,
  QuizBank,
  QuizBankMetadata,
  QuizResult,
  QuizSet,
  QuizBankStats,
  QuizBankApi,
};

export const jtiQuizApi = createQuizBankApi(`${JTI_ADMIN_BASE}/quiz-bank`);

export async function listQuizBanks(language: string = 'zh'): Promise<{ banks: QuizBank[]; total: number; max: number }> {
  return jtiQuizApi.listQuizBanks(language);
}

export async function createQuizBank(language: string, name: string): Promise<QuizBank> {
  return jtiQuizApi.createQuizBank(language, name);
}

export async function deleteQuizBank(language: string, bankId: string): Promise<void> {
  return jtiQuizApi.deleteQuizBank(language, bankId);
}

export async function activateQuizBank(language: string, bankId: string): Promise<void> {
  return jtiQuizApi.activateQuizBank(language, bankId);
}

export async function listQuizQuestions(language: string = 'zh', bankId?: string): Promise<{ questions: QuizQuestion[]; total: number }> {
  return jtiQuizApi.listQuizQuestions(language, bankId);
}

export async function createQuizQuestion(language: string, question: QuizQuestion, bankId?: string): Promise<QuizQuestion> {
  return jtiQuizApi.createQuizQuestion(language, question, bankId);
}

export async function updateQuizQuestion(language: string, id: string, data: Partial<QuizQuestion>, bankId?: string): Promise<QuizQuestion> {
  return jtiQuizApi.updateQuizQuestion(language, id, data, bankId);
}

export async function deleteQuizQuestion(language: string, id: string, bankId?: string): Promise<void> {
  return jtiQuizApi.deleteQuizQuestion(language, id, bankId);
}

export async function listQuizSets(language: string = 'zh'): Promise<{ sets: QuizSet[]; total: number; max: number }> {
  return jtiQuizApi.listQuizSets(language);
}

export async function createQuizSet(language: string, name: string): Promise<QuizSet> {
  return jtiQuizApi.createQuizSet(language, name);
}

export async function deleteQuizSet(language: string, setId: string): Promise<void> {
  return jtiQuizApi.deleteQuizSet(language, setId);
}

export async function activateQuizSet(language: string, setId: string): Promise<void> {
  return jtiQuizApi.activateQuizSet(language, setId);
}

export async function listQuizResults(language: string = 'zh', setId?: string): Promise<{ results: QuizResult[]; total: number }> {
  return jtiQuizApi.listQuizResults(language, setId);
}

export async function updateQuizResult(language: string, quizId: string, data: Partial<QuizResult>, setId?: string): Promise<QuizResult> {
  return jtiQuizApi.updateQuizResult(language, quizId, data, setId);
}

export async function exportQuizResultsCsv(language: string): Promise<void> {
  return jtiQuizApi.exportQuizResultsCsv(language);
}

export async function getQuizBankStats(language: string = 'zh', bankId?: string): Promise<QuizBankStats> {
  return jtiQuizApi.getQuizBankStats(language, bankId);
}

export async function importQuizBank(language: string, bankId: string, file: File, replace = false): Promise<{ count: number; message: string }> {
  return jtiQuizApi.importQuizBank(language, bankId, file, replace);
}

export async function exportQuizBankCsv(language: string, bankId: string): Promise<void> {
  return jtiQuizApi.exportQuizBankCsv(language, bankId);
}

