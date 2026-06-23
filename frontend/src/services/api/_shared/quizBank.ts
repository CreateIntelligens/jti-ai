import { extractErrorMessage, fetchAsAdmin, handleResponse, normLang, buildUrl } from '../base';
import { downloadBlob } from '../../../utils/download';

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

export interface QuizBankApi {
  listQuizBanks(language?: string): Promise<{ banks: QuizBank[]; total: number; max: number }>;
  createQuizBank(language: string, name: string): Promise<QuizBank>;
  deleteQuizBank(language: string, bankId: string): Promise<void>;
  activateQuizBank(language: string, bankId: string): Promise<void>;
  listQuizQuestions(language?: string, bankId?: string): Promise<{ questions: QuizQuestion[]; total: number }>;
  createQuizQuestion(language: string, question: QuizQuestion, bankId?: string): Promise<QuizQuestion>;
  updateQuizQuestion(language: string, id: string, data: Partial<QuizQuestion>, bankId?: string): Promise<QuizQuestion>;
  deleteQuizQuestion(language: string, id: string, bankId?: string): Promise<void>;
  listQuizSets(language?: string): Promise<{ sets: QuizSet[]; total: number; max: number }>;
  createQuizSet(language: string, name: string): Promise<QuizSet>;
  deleteQuizSet(language: string, setId: string): Promise<void>;
  activateQuizSet(language: string, setId: string): Promise<void>;
  listQuizResults(language?: string, setId?: string): Promise<{ results: QuizResult[]; total: number }>;
  updateQuizResult(language: string, quizId: string, data: Partial<QuizResult>, setId?: string): Promise<QuizResult>;
  exportQuizResultsCsv(language: string): Promise<void>;
  getQuizBankStats(language?: string, bankId?: string): Promise<QuizBankStats>;
  importQuizBank(language: string, bankId: string, file: File, replace?: boolean): Promise<{ count: number; message: string }>;
  exportQuizBankCsv(language: string, bankId: string): Promise<void>;
}

export function createQuizBankApi(basePath: string): QuizBankApi {
  function buildApiUrl(path: string, language: string = 'zh', extraParams?: Record<string, string | number | boolean>) {
    return buildUrl(`${basePath}${path}`, { language: normLang(language), ...extraParams });
  }

  type ApiMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  type ApiParams = Record<string, string | number | boolean>;

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
    const response = await fetchAsAdmin(buildApiUrl(path, language, params), options);
    return handleResponse<T>(response);
  }

  return {
    async listQuizBanks(language = 'zh') {
      return apiCall('GET', '/banks/', language);
    },
    async createQuizBank(language, name) {
      return apiCall('POST', '/banks/', language, { name });
    },
    async deleteQuizBank(language, bankId) {
      return apiCall('DELETE', `/banks/${encodeURIComponent(bankId)}`, language);
    },
    async activateQuizBank(language, bankId) {
      return apiCall('POST', `/banks/${encodeURIComponent(bankId)}/activate`, language);
    },
    async listQuizQuestions(language = 'zh', bankId) {
      return apiCall('GET', '/questions/', language, undefined, bankId ? { bank_id: bankId } : {});
    },
    async createQuizQuestion(language, question, bankId) {
      return apiCall('POST', '/questions/', language, question, bankId ? { bank_id: bankId } : {});
    },
    async updateQuizQuestion(language, id, data, bankId) {
      return apiCall('PUT', `/questions/${encodeURIComponent(id)}`, language, data, bankId ? { bank_id: bankId } : {});
    },
    async deleteQuizQuestion(language, id, bankId) {
      return apiCall('DELETE', `/questions/${encodeURIComponent(id)}`, language, undefined, bankId ? { bank_id: bankId } : {});
    },
    async listQuizSets(language = 'zh') {
      return apiCall('GET', '/quiz-results/sets/', language);
    },
    async createQuizSet(language, name) {
      return apiCall('POST', '/quiz-results/sets/', language, { name });
    },
    async deleteQuizSet(language, setId) {
      return apiCall('DELETE', `/quiz-results/sets/${encodeURIComponent(setId)}`, language);
    },
    async activateQuizSet(language, setId) {
      return apiCall('POST', `/quiz-results/sets/${encodeURIComponent(setId)}/activate`, language);
    },
    async listQuizResults(language = 'zh', setId) {
      return apiCall('GET', '/quiz-results/', language, undefined, setId ? { set_id: setId } : {});
    },
    async updateQuizResult(language, quizId, data, setId) {
      return apiCall('PUT', `/quiz-results/${encodeURIComponent(quizId)}`, language, data, setId ? { set_id: setId } : {});
    },
    async exportQuizResultsCsv(language) {
      const response = await fetchAsAdmin(buildApiUrl('/transfer/export', language, { type: 'results' }));
      if (!response.ok) throw new Error(await extractErrorMessage(response));
      downloadBlob(await response.blob(), `quiz_results_${language}.csv`);
    },
    async getQuizBankStats(language = 'zh', bankId) {
      return apiCall('GET', '/stats/', language, undefined, bankId ? { bank_id: bankId } : {});
    },
    async importQuizBank(language, bankId, file, replace = false) {
      const extra: Record<string, string> = { bank_id: bankId, type: 'questions' };
      if (replace) extra.replace = 'true';
      const formData = new FormData();
      formData.append('file', file);
      const response = await fetchAsAdmin(buildApiUrl('/transfer/import', language, extra), { method: 'POST', body: formData });
      return handleResponse(response);
    },
    async exportQuizBankCsv(language, bankId) {
      const response = await fetchAsAdmin(buildApiUrl('/transfer/export', language, { bank_id: bankId, type: 'questions' }));
      if (!response.ok) throw new Error(await extractErrorMessage(response));
      downloadBlob(await response.blob(), `quiz_bank_${bankId}_${language}.csv`);
    }
  };
}
