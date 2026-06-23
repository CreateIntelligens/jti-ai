import { API_BASE, buildUrl, fetchAsAdmin, handleResponse, normLang } from '../base';
import type { QaMergedCsvResponse } from './qaKnowledge';
import type { QaAdminCategory, QaCategory } from '../../../config/qaTopics';

// Topic API for "fixed apps" (jti / esg) whose topics live under
//   public_router → /api/<app>            （/topics/{lang}, /topics/{lang}/all）
//   admin router  → /api/<app>-admin/topics（建立/排序/刪除/可見性/更新）
//   merged csv    → /api/<app>-admin/knowledge/topic-csv-merged
// jti and esg are byte-for-byte symmetric apart from the route prefix, so the
// whole surface is built from `app` via closure here. Topics are single-language
// end-to-end (label per request); `topic_id` may contain "/" so it is passed
// raw, never encoded.

type TopicUpdatePayload = {
  labels?: string;
  category_labels?: string;
  questions?: string[];
  hidden_questions?: string[];
  hidden?: boolean;
};

export interface FixedAppTopicApi {
  /** 公開：只含可見的 topics/questions（過濾隱藏）。 */
  listTopics(language: string): Promise<{ categories: QaCategory[] }>;
  /** Admin：完整 topics（含隱藏），供文件工作區管理。 */
  listTopicsAdmin(language: string): Promise<{ categories: QaAdminCategory[] }>;
  setCategoryHidden(
    categoryId: string,
    hidden: boolean,
    language: string,
  ): Promise<{ category_id: string; hidden: boolean }>;
  getTopicMergedCsv(topicId: string, language: string): Promise<QaMergedCsvResponse>;
  createTopic(
    topicId: string,
    label: string,
    categoryLabel: string,
    questions: string[] | undefined,
    language: string,
  ): Promise<Record<string, unknown>>;
  updateTopic(
    topicId: string,
    data: TopicUpdatePayload,
    language: string,
  ): Promise<Record<string, unknown>>;
  reorderTopics(topicIds: string[], language: string): Promise<{ updated: number }>;
  deleteTopic(topicId: string, language: string): Promise<void>;
  deleteTopics(topicIds: string[], language: string): Promise<{ deleted: number }>;
}

/** Shared JSON RequestInit builder for the fixed-app topic/knowledge clients. */
export function jsonRequest(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  };
}

/**
 * Build the full topic client (public + admin) bound to one fixed app.
 * @param app app key used in the route prefix (e.g. 'jti' → `/api/jti/...`).
 */
export function createFixedAppTopicApi(app: string): FixedAppTopicApi {
  const publicBase = `${API_BASE}/${app}`;
  const adminBase = `${API_BASE}/${app}-admin/topics`;

  async function adminJson<T>(path: string, options?: RequestInit): Promise<T> {
    const response = await fetchAsAdmin(`${adminBase}${path}`, options);
    return handleResponse<T>(response);
  }

  function topicPath(language: string, topicId?: string): string {
    const base = `/${normLang(language)}`;
    return topicId ? `${base}/${topicId}` : `${base}/`;
  }

  return {
    async listTopics(language) {
      const res = await fetchAsAdmin(`${publicBase}/topics/${normLang(language)}`);
      return handleResponse(res);
    },
    async listTopicsAdmin(language) {
      const res = await fetchAsAdmin(`${publicBase}/topics/${normLang(language)}/all`);
      return handleResponse(res);
    },
    async setCategoryHidden(categoryId, hidden, language) {
      const res = await fetchAsAdmin(
        `${adminBase}/categories/${normLang(language)}/${encodeURIComponent(categoryId)}/visibility`,
        jsonRequest('PUT', { hidden }),
      );
      return handleResponse(res);
    },
    async getTopicMergedCsv(topicId, language) {
      const res = await fetchAsAdmin(
        buildUrl(`${API_BASE}/${app}-admin/knowledge/topic-csv-merged`, {
          topic_id: topicId,
          language: normLang(language),
        }),
      );
      return handleResponse<QaMergedCsvResponse>(res);
    },
    createTopic(topicId, label, categoryLabel, questions, language) {
      return adminJson<Record<string, unknown>>(
        topicPath(language),
        jsonRequest('POST', {
          topic_id: topicId,
          labels: label,
          category_labels: categoryLabel,
          questions: questions ?? [],
        }),
      );
    },
    updateTopic(topicId, data, language) {
      return adminJson<Record<string, unknown>>(
        topicPath(language, topicId),
        jsonRequest('PUT', data),
      );
    },
    reorderTopics(topicIds, language) {
      return adminJson<{ updated: number }>(
        topicPath(language, 'reorder'),
        jsonRequest('PUT', { topic_ids: topicIds }),
      );
    },
    async deleteTopic(topicId, language) {
      await adminJson<void>(topicPath(language, topicId), { method: 'DELETE' });
    },
    deleteTopics(topicIds, language) {
      return adminJson<{ deleted: number }>(
        `/${normLang(language)}/delete-batch`,
        jsonRequest('POST', { topic_ids: topicIds }),
      );
    },
  };
}
