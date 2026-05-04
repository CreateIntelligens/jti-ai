import { API_BASE, fetchAsAdmin, handleResponse, normLang } from './base';
import { downloadBlob } from '../../utils/download';

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
  tts_character?: string;
}

export interface JtiRuntimeSettingsResponse {
  prompt_id?: string;
  settings: JtiRuntimeSettings;
}


const JTI_ADMIN_BASE = `${API_BASE}/jti-admin`;

function jtiUrl(path: string, language: string = 'zh', extraParams?: Record<string, string>): string {
  const params = new URLSearchParams({ language: normLang(language), ...extraParams });
  return `${JTI_ADMIN_BASE}${path}?${params}`;
}

export async function listJtiPrompts(language: string = 'zh'): Promise<any> {
  const response = await fetchAsAdmin(jtiUrl('/prompts/', language));
  return handleResponse<any>(response);
}

export async function createJtiPrompt(name: string, content: string, language: string = 'zh'): Promise<any> {
  const response = await fetchAsAdmin(jtiUrl('/prompts/', language), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, content }),
  });
  return handleResponse<any>(response);
}

export async function updateJtiPrompt(promptId: string, name?: string, content?: string, language: string = 'zh'): Promise<any> {
  const response = await fetchAsAdmin(jtiUrl(`/prompts/${promptId}`, language), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, content }),
  });
  return handleResponse<any>(response);
}

export async function deleteJtiPrompt(promptId: string, language: string = 'zh'): Promise<void> {
  const response = await fetchAsAdmin(jtiUrl(`/prompts/${promptId}`, language), { method: 'DELETE' });
  await handleResponse<void>(response);
}

export async function setActiveJtiPrompt(promptId: string | null, language: string = 'zh'): Promise<void> {
  const response = await fetchAsAdmin(jtiUrl('/prompts/active', language), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt_id: promptId }),
  });
  await handleResponse<void>(response);
}

export async function cloneDefaultJtiPrompt(language: string = 'zh'): Promise<any> {
  const response = await fetchAsAdmin(jtiUrl('/prompts/clone', language), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  return handleResponse<any>(response);
}

export async function getJtiRuntimeSettings(promptId?: string, language: string = 'zh'): Promise<JtiRuntimeSettingsResponse> {
  const response = await fetchAsAdmin(jtiUrl('/prompts/runtime-settings', language, promptId ? { prompt_id: promptId } : {}), { method: 'GET' });
  return handleResponse<JtiRuntimeSettingsResponse>(response);
}

export async function updateJtiRuntimeSettings(
  settings: JtiRuntimeSettings,
  promptId?: string,
  language: string = 'zh',
): Promise<{ settings: JtiRuntimeSettings; message: string; prompt_id?: string }> {
  const response = await fetchAsAdmin(jtiUrl('/prompts/runtime-settings', language), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...settings, prompt_id: promptId }),
  });
  return handleResponse(response);
}

// ========== JTI 知識庫管理 ==========

export async function listJtiKnowledgeFiles(language: string = 'zh'): Promise<any> {
  const response = await fetchAsAdmin(jtiUrl('/knowledge/files/', language));
  return handleResponse<any>(response);
}

export async function getJtiKnowledgeFileContent(filename: string, language: string = 'zh'): Promise<any> {
  const response = await fetchAsAdmin(jtiUrl(`/knowledge/files/${encodeURIComponent(filename)}/content`, language));
  return handleResponse<any>(response);
}

export async function downloadJtiKnowledgeFile(filename: string, language: string = 'zh'): Promise<void> {
  window.open(jtiUrl(`/knowledge/files/${encodeURIComponent(filename)}/download`, language), '_blank');
}

export async function updateJtiKnowledgeFileContent(filename: string, content: string, language: string = 'zh'): Promise<any> {
  const response = await fetchAsAdmin(jtiUrl(`/knowledge/files/${encodeURIComponent(filename)}/content`, language), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });
  return handleResponse<any>(response);
}

export async function uploadJtiKnowledgeFile(language: string, file: File): Promise<any> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetchAsAdmin(jtiUrl('/knowledge/upload/', language), {
    method: 'POST',
    body: formData,
  });
  return handleResponse<any>(response);
}

export async function deleteJtiKnowledgeFile(fileName: string, language: string = 'zh'): Promise<any> {
  const response = await fetchAsAdmin(jtiUrl(`/knowledge/files/${encodeURIComponent(fileName)}`, language), {
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
  const response = await fetchAsAdmin(jtiUrl('/quiz-bank/banks/', language));
  return handleResponse(response);
}

export async function createQuizBank(language: string, name: string): Promise<QuizBank> {
  const response = await fetchAsAdmin(jtiUrl('/quiz-bank/banks/', language), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  return handleResponse(response);
}

export async function deleteQuizBank(language: string, bankId: string): Promise<void> {
  const response = await fetchAsAdmin(jtiUrl(`/quiz-bank/banks/${encodeURIComponent(bankId)}`, language), {
    method: 'DELETE',
  });
  await handleResponse(response);
}

export async function activateQuizBank(language: string, bankId: string): Promise<void> {
  const response = await fetchAsAdmin(jtiUrl(`/quiz-bank/banks/${encodeURIComponent(bankId)}/activate`, language), {
    method: 'POST',
  });
  await handleResponse(response);
}

export async function listQuizQuestions(language: string = 'zh', bankId?: string): Promise<{ questions: QuizQuestion[]; total: number }> {
  const response = await fetchAsAdmin(jtiUrl('/quiz-bank/questions/', language, bankId ? { bank_id: bankId } : {}));
  return handleResponse(response);
}

export async function getQuizQuestion(language: string, id: string, bankId?: string): Promise<QuizQuestion> {
  const response = await fetchAsAdmin(jtiUrl(`/quiz-bank/questions/${encodeURIComponent(id)}`, language, bankId ? { bank_id: bankId } : {}));
  return handleResponse(response);
}

export async function createQuizQuestion(language: string, question: QuizQuestion, bankId?: string): Promise<QuizQuestion> {
  const response = await fetchAsAdmin(jtiUrl('/quiz-bank/questions/', language, bankId ? { bank_id: bankId } : {}), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(question),
  });
  return handleResponse(response);
}

export async function updateQuizQuestion(language: string, id: string, data: Partial<QuizQuestion>, bankId?: string): Promise<QuizQuestion> {
  const response = await fetchAsAdmin(jtiUrl(`/quiz-bank/questions/${encodeURIComponent(id)}`, language, bankId ? { bank_id: bankId } : {}), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse(response);
}

export async function deleteQuizQuestion(language: string, id: string, bankId?: string): Promise<void> {
  const response = await fetchAsAdmin(jtiUrl(`/quiz-bank/questions/${encodeURIComponent(id)}`, language, bankId ? { bank_id: bankId } : {}), {
    method: 'DELETE',
  });
  await handleResponse(response);
}

export async function getQuizBankMetadata(language: string = 'zh', bankId: string = 'default'): Promise<QuizBankMetadata> {
  const response = await fetchAsAdmin(jtiUrl(`/quiz-bank/banks/${encodeURIComponent(bankId)}`, language));
  return handleResponse(response);
}

export async function updateQuizBankMetadata(language: string, data: Partial<QuizBankMetadata>, bankId: string = 'default'): Promise<QuizBankMetadata> {
  const response = await fetchAsAdmin(jtiUrl(`/quiz-bank/banks/${encodeURIComponent(bankId)}`, language), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse(response);
}

export async function listQuizSets(language: string = 'zh'): Promise<{ sets: QuizSet[]; total: number; max: number }> {
  const response = await fetchAsAdmin(jtiUrl('/quiz-bank/quiz-results/sets/', language));
  return handleResponse(response);
}

export async function createQuizSet(language: string, name: string): Promise<QuizSet> {
  const response = await fetchAsAdmin(jtiUrl('/quiz-bank/quiz-results/sets/', language), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  return handleResponse(response);
}

export async function deleteQuizSet(language: string, setId: string): Promise<void> {
  const response = await fetchAsAdmin(jtiUrl(`/quiz-bank/quiz-results/sets/${encodeURIComponent(setId)}`, language), {
    method: 'DELETE',
  });
  await handleResponse(response);
}

export async function activateQuizSet(language: string, setId: string): Promise<void> {
  const response = await fetchAsAdmin(jtiUrl(`/quiz-bank/quiz-results/sets/${encodeURIComponent(setId)}/activate`, language), {
    method: 'POST',
  });
  await handleResponse(response);
}

export async function listQuizResults(language: string = 'zh', setId?: string): Promise<{ results: QuizResult[]; total: number }> {
  const response = await fetchAsAdmin(jtiUrl('/quiz-bank/quiz-results/', language, setId ? { set_id: setId } : {}));
  return handleResponse(response);
}

export async function updateQuizResult(language: string, quizId: string, data: Partial<QuizResult>, setId?: string): Promise<QuizResult> {
  const response = await fetchAsAdmin(jtiUrl(`/quiz-bank/quiz-results/${encodeURIComponent(quizId)}`, language, setId ? { set_id: setId } : {}), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse(response);
}

export async function exportQuizResultsCsv(language: string): Promise<void> {
  const response = await fetchAsAdmin(jtiUrl('/quiz-bank/transfer/export', language, { type: 'results' }));
  if (!response.ok) throw new Error('Export failed');
  downloadBlob(await response.blob(), `quiz_results_${language}.csv`);
}

export async function getQuizBankStats(language: string = 'zh', bankId?: string): Promise<QuizBankStats> {
  const response = await fetchAsAdmin(jtiUrl('/quiz-bank/stats/', language, bankId ? { bank_id: bankId } : {}));
  return handleResponse(response);
}

export async function importQuizBank(language: string, bankId: string, file: File, replace = false): Promise<{ count: number; message: string }> {
  const extra: Record<string, string> = { bank_id: bankId, type: 'questions' };
  if (replace) extra.replace = 'true';
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetchAsAdmin(jtiUrl('/quiz-bank/transfer/import', language, extra), {
    method: 'POST',
    body: formData,
  });
  return handleResponse(response);
}

export async function exportQuizBankCsv(language: string, bankId: string): Promise<void> {
  const response = await fetchAsAdmin(jtiUrl('/quiz-bank/transfer/export', language, { bank_id: bankId, type: 'questions' }));
  if (!response.ok) throw new Error('Export failed');
  downloadBlob(await response.blob(), `quiz_bank_${bankId}_${language}.csv`);
}
