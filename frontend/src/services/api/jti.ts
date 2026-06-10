import { API_BASE, fetchAsAdmin, handleResponse, normLang, buildUrl } from './base';
import { downloadBlob } from '../../utils/download';

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

export interface QuizQuestionOption {
  id: string;
  text: string;
  score: Record<string, number>;
}

export interface QuizQuestion {
  id: string;
  text: string;
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
  };
  is_active: boolean;
  is_default: boolean;
}

export interface QuizResult {
  quiz_id: string;
  title: string;
  color_name: string;
  recommended_colors: string[];
  description: string;
}

export interface QuizSet {
  set_id: string;
  name: string;
  language: string;
  is_active: boolean;
  is_default: boolean;
  quiz_count: number;
}

export interface QuizBankStats {
  total_questions: number;
  categories: Record<string, number>;
  dimensions: string[];
  selection_rules: Record<string, unknown>;
}

export async function listQuizBanks(language: string = 'zh'): Promise<{ banks: QuizBank[]; total: number; max: number }> {
  return apiCall('GET', '/quiz-bank/banks/', language);
}

export async function createQuizBank(language: string, name: string): Promise<QuizBank> {
  return apiCall('POST', '/quiz-bank/banks/', language, { name });
}

export async function deleteQuizBank(language: string, bankId: string): Promise<void> {
  return apiCall('DELETE', `/quiz-bank/banks/${encodeURIComponent(bankId)}`, language);
}

export async function activateQuizBank(language: string, bankId: string): Promise<void> {
  return apiCall('POST', `/quiz-bank/banks/${encodeURIComponent(bankId)}/activate`, language);
}

export async function listQuizQuestions(language: string = 'zh', bankId?: string): Promise<{ questions: QuizQuestion[]; total: number }> {
  return apiCall('GET', '/quiz-bank/questions/', language, undefined, bankId ? { bank_id: bankId } : {});
}

export async function getQuizQuestion(language: string, id: string, bankId?: string): Promise<QuizQuestion> {
  return apiCall('GET', `/quiz-bank/questions/${encodeURIComponent(id)}`, language, undefined, bankId ? { bank_id: bankId } : {});
}

export async function createQuizQuestion(language: string, question: QuizQuestion, bankId?: string): Promise<QuizQuestion> {
  return apiCall('POST', '/quiz-bank/questions/', language, question, bankId ? { bank_id: bankId } : {});
}

export async function updateQuizQuestion(language: string, id: string, data: Partial<QuizQuestion>, bankId?: string): Promise<QuizQuestion> {
  return apiCall('PUT', `/quiz-bank/questions/${encodeURIComponent(id)}`, language, data, bankId ? { bank_id: bankId } : {});
}

export async function deleteQuizQuestion(language: string, id: string, bankId?: string): Promise<void> {
  return apiCall('DELETE', `/quiz-bank/questions/${encodeURIComponent(id)}`, language, undefined, bankId ? { bank_id: bankId } : {});
}

export async function getQuizBankMetadata(language: string = 'zh', bankId: string = 'default'): Promise<QuizBankMetadata> {
  return apiCall('GET', `/quiz-bank/banks/${encodeURIComponent(bankId)}`, language);
}

export async function updateQuizBankMetadata(language: string, data: Partial<QuizBankMetadata>, bankId: string = 'default'): Promise<QuizBankMetadata> {
  return apiCall('PATCH', `/quiz-bank/banks/${encodeURIComponent(bankId)}`, language, data);
}

export async function listQuizSets(language: string = 'zh'): Promise<{ sets: QuizSet[]; total: number; max: number }> {
  return apiCall('GET', '/quiz-bank/quiz-results/sets/', language);
}

export async function createQuizSet(language: string, name: string): Promise<QuizSet> {
  return apiCall('POST', '/quiz-bank/quiz-results/sets/', language, { name });
}

export async function deleteQuizSet(language: string, setId: string): Promise<void> {
  return apiCall('DELETE', `/quiz-bank/quiz-results/sets/${encodeURIComponent(setId)}`, language);
}

export async function activateQuizSet(language: string, setId: string): Promise<void> {
  return apiCall('POST', `/quiz-bank/quiz-results/sets/${encodeURIComponent(setId)}/activate`, language);
}

export async function listQuizResults(language: string = 'zh', setId?: string): Promise<{ results: QuizResult[]; total: number }> {
  return apiCall('GET', '/quiz-bank/quiz-results/', language, undefined, setId ? { set_id: setId } : {});
}

export async function updateQuizResult(language: string, quizId: string, data: Partial<QuizResult>, setId?: string): Promise<QuizResult> {
  return apiCall('PUT', `/quiz-bank/quiz-results/${encodeURIComponent(quizId)}`, language, data, setId ? { set_id: setId } : {});
}

export async function exportQuizResultsCsv(language: string): Promise<void> {
  const response = await fetchAsAdmin(jtiUrl('/quiz-bank/transfer/export', language, { type: 'results' }));
  if (!response.ok) throw new Error('Export failed');
  downloadBlob(await response.blob(), `quiz_results_${language}.csv`);
}

export async function getQuizBankStats(language: string = 'zh', bankId?: string): Promise<QuizBankStats> {
  return apiCall('GET', '/quiz-bank/stats/', language, undefined, bankId ? { bank_id: bankId } : {});
}

export async function importQuizBank(language: string, bankId: string, file: File, replace = false): Promise<{ count: number; message: string }> {
  const extra: Record<string, string> = { bank_id: bankId, type: 'questions' };
  if (replace) extra.replace = 'true';
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetchAsAdmin(jtiUrl('/quiz-bank/transfer/import', language, extra), { method: 'POST', body: formData });
  return handleResponse(response);
}

export async function exportQuizBankCsv(language: string, bankId: string): Promise<void> {
  const response = await fetchAsAdmin(jtiUrl('/quiz-bank/transfer/export', language, { bank_id: bankId, type: 'questions' }));
  if (!response.ok) throw new Error('Export failed');
  downloadBlob(await response.blob(), `quiz_bank_${bankId}_${language}.csv`);
}
