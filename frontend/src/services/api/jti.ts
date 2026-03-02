import { API_BASE, fetchAsAdmin, handleResponse } from './base';

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
    zh: { title: string; description: string };
    en: { title: string; description: string };
  };
  max_response_chars: number;
}

export interface JtiRuntimeSettingsResponse {
  prompt_id?: string;
  settings: JtiRuntimeSettings;
}

function normLang(language: string): string {
  return language.toLowerCase().startsWith('en') ? 'en' : 'zh';
}

const JTI_ADMIN_BASE = `${API_BASE}/jti-admin`;

export async function listJtiPrompts(language: string = 'zh'): Promise<any> {
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/prompts/?language=${normLang(language)}`);
  return handleResponse<any>(response);
}

export async function createJtiPrompt(name: string, content: string, language: string = 'zh'): Promise<any> {
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/prompts/?language=${normLang(language)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, content }),
  });
  return handleResponse<any>(response);
}

export async function updateJtiPrompt(promptId: string, name?: string, content?: string, language: string = 'zh'): Promise<any> {
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/prompts/${promptId}?language=${normLang(language)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, content }),
  });
  return handleResponse<any>(response);
}

export async function deleteJtiPrompt(promptId: string, language: string = 'zh'): Promise<void> {
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/prompts/${promptId}?language=${normLang(language)}`, {
    method: 'DELETE',
  });
  await handleResponse<void>(response);
}

export async function setActiveJtiPrompt(promptId: string | null, language: string = 'zh'): Promise<void> {
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/prompts/active?language=${normLang(language)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt_id: promptId }),
  });
  await handleResponse<void>(response);
}

export async function cloneDefaultJtiPrompt(language: string = 'zh'): Promise<any> {
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/prompts/clone?language=${normLang(language)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  return handleResponse<any>(response);
}

export async function getJtiRuntimeSettings(promptId?: string, language: string = 'zh'): Promise<JtiRuntimeSettingsResponse> {
  const query = new URLSearchParams({ language: normLang(language) });
  if (promptId) query.set('prompt_id', promptId);
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/prompts/runtime-settings?${query}`, { method: 'GET' });
  return handleResponse<JtiRuntimeSettingsResponse>(response);
}

export async function updateJtiRuntimeSettings(
  settings: JtiRuntimeSettings,
  promptId?: string,
  language: string = 'zh',
): Promise<{ settings: JtiRuntimeSettings; message: string; prompt_id?: string }> {
  const payload = promptId ? { ...settings, prompt_id: promptId } : settings;
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/prompts/runtime-settings?language=${normLang(language)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse(response);
}

// ========== JTI 知識庫管理 ==========

export async function listJtiKnowledgeFiles(language: string = 'zh'): Promise<any> {
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/knowledge/files/?language=${language}`);
  return handleResponse<any>(response);
}

export async function getJtiKnowledgeFileContent(filename: string, language: string = 'zh'): Promise<any> {
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/knowledge/files/${encodeURIComponent(filename)}/content?language=${language}`);
  return handleResponse<any>(response);
}

export async function downloadJtiKnowledgeFile(filename: string, language: string = 'zh'): Promise<void> {
  const params = new URLSearchParams({ language });
  window.open(`${JTI_ADMIN_BASE}/knowledge/files/${encodeURIComponent(filename)}/download?${params}`, '_blank');
}

export async function updateJtiKnowledgeFileContent(filename: string, content: string, language: string = 'zh'): Promise<any> {
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/knowledge/files/${encodeURIComponent(filename)}/content?language=${language}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });
  return handleResponse<any>(response);
}

export async function uploadJtiKnowledgeFile(language: string, file: File): Promise<any> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/knowledge/upload/?language=${language}`, {
    method: 'POST',
    body: formData,
  });
  return handleResponse<any>(response);
}

export async function deleteJtiKnowledgeFile(fileName: string, language: string = 'zh'): Promise<any> {
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/knowledge/files/${encodeURIComponent(fileName)}?language=${language}`, {
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

export interface ColorResult {
  color_id: string;
  title: string;
  color_name: string;
  recommended_colors: string[];
  description: string;
}

export interface ColorSet {
  set_id: string;
  name: string;
  language: string;
  is_active: boolean;
  is_default: boolean;
  color_count: number;
}

export interface QuizBankStats {
  total_questions: number;
  categories: Record<string, number>;
  dimensions: string[];
  selection_rules: Record<string, unknown>;
}

export async function listQuizBanks(language: string = 'zh'): Promise<{ banks: QuizBank[]; total: number; max: number }> {
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/quiz-bank/banks/?language=${language}`);
  return handleResponse(response);
}

export async function createQuizBank(language: string, name: string): Promise<QuizBank> {
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/quiz-bank/banks/?language=${language}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  return handleResponse(response);
}

export async function deleteQuizBank(language: string, bankId: string): Promise<void> {
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/quiz-bank/banks/${encodeURIComponent(bankId)}?language=${language}`, {
    method: 'DELETE',
  });
  await handleResponse(response);
}

export async function activateQuizBank(language: string, bankId: string): Promise<void> {
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/quiz-bank/banks/${encodeURIComponent(bankId)}/activate?language=${language}`, {
    method: 'POST',
  });
  await handleResponse(response);
}

export async function listQuizQuestions(language: string = 'zh', bankId?: string): Promise<{ questions: QuizQuestion[]; total: number }> {
  const params = new URLSearchParams({ language });
  if (bankId) params.set('bank_id', bankId);
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/quiz-bank/questions/?${params}`);
  return handleResponse(response);
}

export async function getQuizQuestion(language: string, id: string, bankId?: string): Promise<QuizQuestion> {
  const params = new URLSearchParams({ language });
  if (bankId) params.set('bank_id', bankId);
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/quiz-bank/questions/${encodeURIComponent(id)}?${params}`);
  return handleResponse(response);
}

export async function createQuizQuestion(language: string, question: QuizQuestion, bankId?: string): Promise<QuizQuestion> {
  const params = new URLSearchParams({ language });
  if (bankId) params.set('bank_id', bankId);
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/quiz-bank/questions/?${params}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(question),
  });
  return handleResponse(response);
}

export async function updateQuizQuestion(language: string, id: string, data: Partial<QuizQuestion>, bankId?: string): Promise<QuizQuestion> {
  const params = new URLSearchParams({ language });
  if (bankId) params.set('bank_id', bankId);
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/quiz-bank/questions/${encodeURIComponent(id)}?${params}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse(response);
}

export async function deleteQuizQuestion(language: string, id: string, bankId?: string): Promise<void> {
  const params = new URLSearchParams({ language });
  if (bankId) params.set('bank_id', bankId);
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/quiz-bank/questions/${encodeURIComponent(id)}?${params}`, {
    method: 'DELETE',
  });
  await handleResponse(response);
}

export async function getQuizBankMetadata(language: string = 'zh', bankId: string = 'default'): Promise<QuizBankMetadata> {
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/quiz-bank/banks/${encodeURIComponent(bankId)}?language=${language}`);
  return handleResponse(response);
}

export async function updateQuizBankMetadata(language: string, data: Partial<QuizBankMetadata>, bankId: string = 'default'): Promise<QuizBankMetadata> {
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/quiz-bank/banks/${encodeURIComponent(bankId)}?language=${language}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse(response);
}

export async function listColorSets(language: string = 'zh'): Promise<{ sets: ColorSet[]; total: number; max: number }> {
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/quiz-bank/color-results/sets/?language=${language}`);
  return handleResponse(response);
}

export async function createColorSet(language: string, name: string): Promise<ColorSet> {
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/quiz-bank/color-results/sets/?language=${language}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  return handleResponse(response);
}

export async function deleteColorSet(language: string, setId: string): Promise<void> {
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/quiz-bank/color-results/sets/${encodeURIComponent(setId)}?language=${language}`, {
    method: 'DELETE',
  });
  await handleResponse(response);
}

export async function activateColorSet(language: string, setId: string): Promise<void> {
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/quiz-bank/color-results/sets/${encodeURIComponent(setId)}/activate?language=${language}`, {
    method: 'POST',
  });
  await handleResponse(response);
}

export async function listColorResults(language: string = 'zh', setId?: string): Promise<{ results: ColorResult[]; total: number }> {
  const params = new URLSearchParams({ language });
  if (setId) params.set('set_id', setId);
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/quiz-bank/color-results/?${params}`);
  return handleResponse(response);
}

export async function updateColorResult(language: string, colorId: string, data: Partial<ColorResult>, setId?: string): Promise<ColorResult> {
  const params = new URLSearchParams({ language });
  if (setId) params.set('set_id', setId);
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/quiz-bank/color-results/${encodeURIComponent(colorId)}?${params}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse(response);
}

export async function exportColorResultsCsv(language: string): Promise<void> {
  const params = new URLSearchParams({ language, type: 'colors' });
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/quiz-bank/transfer/export?${params}`);
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

export async function getQuizBankStats(language: string = 'zh', bankId?: string): Promise<QuizBankStats> {
  const params = new URLSearchParams({ language });
  if (bankId) params.set('bank_id', bankId);
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/quiz-bank/stats/?${params}`);
  return handleResponse(response);
}

export async function importQuizBank(language: string, bankId: string, file: File, replace = false): Promise<{ count: number; message: string }> {
  const params = new URLSearchParams({ language, bank_id: bankId, type: 'questions' });
  if (replace) params.set('replace', 'true');
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/quiz-bank/transfer/import?${params}`, {
    method: 'POST',
    body: formData,
  });
  return handleResponse(response);
}

export async function exportQuizBankCsv(language: string, bankId: string): Promise<void> {
  const params = new URLSearchParams({ language, bank_id: bankId, type: 'questions' });
  const response = await fetchAsAdmin(`${JTI_ADMIN_BASE}/quiz-bank/transfer/export?${params}`);
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
