import { API_BASE } from './base';
import { createQaKnowledgeApi, type QaMergedCsvResponse, type SaveTopicCsvMergedPayload } from './_shared/qaKnowledge';
import { createFixedAppTopicApi } from './_shared/fixedAppTopics';
import type { QaAdminCategory, QaCategory } from '../../config/qaTopics';

// ESG 固定庫的 index Q&A topics / knowledge API。
// ESG 與 JTI 完全對稱，差別只在路由前綴（esg vs jti），整個 surface 由 factory
// 依 app 產生；以下 named export 為轉接層，維持既有呼叫端與測試介面不變。

export const esgTopicApi = createFixedAppTopicApi('esg');
export const esgQaKnowledgeApi = createQaKnowledgeApi(`${API_BASE}/esg-admin/knowledge`);

// ===== Topics =====

export function listEsgTopics(language: string): Promise<{ categories: QaCategory[] }> {
  return esgTopicApi.listTopics(language);
}

export function listEsgTopicsAdmin(language: string): Promise<{ categories: QaAdminCategory[] }> {
  return esgTopicApi.listTopicsAdmin(language);
}

export function setEsgCategoryHidden(categoryId: string, hidden: boolean, language: string) {
  return esgTopicApi.setCategoryHidden(categoryId, hidden, language);
}

export function getEsgTopicMergedCsv(topicId: string, language: string): Promise<QaMergedCsvResponse> {
  return esgTopicApi.getTopicMergedCsv(topicId, language);
}

export function createEsgTopic(
  topicId: string,
  label: string,
  categoryLabel: string,
  questions: string[] | undefined,
  language: string,
) {
  return esgTopicApi.createTopic(topicId, label, categoryLabel, questions, language);
}

export function updateEsgTopic(
  topicId: string,
  data: { labels?: string; category_labels?: string; questions?: string[]; hidden_questions?: string[]; hidden?: boolean },
  language: string,
) {
  return esgTopicApi.updateTopic(topicId, data, language);
}

export function reorderEsgTopics(topicIds: string[], language: string) {
  return esgTopicApi.reorderTopics(topicIds, language);
}

export function deleteEsgTopic(topicId: string, language: string) {
  return esgTopicApi.deleteTopic(topicId, language);
}

export function deleteEsgTopics(topicIds: string[], language: string) {
  return esgTopicApi.deleteTopics(topicIds, language);
}

// ===== Knowledge files / merged CSV =====

export function listEsgKnowledgeFiles(language: string = 'zh') {
  return esgQaKnowledgeApi.listKnowledgeFiles(language);
}

export function getEsgKnowledgeFileContent(filename: string, language: string = 'zh') {
  return esgQaKnowledgeApi.getKnowledgeFileContent(filename, language);
}

export function downloadEsgKnowledgeFile(filename: string, language: string = 'zh') {
  esgQaKnowledgeApi.downloadKnowledgeFile(filename, language);
}

export function updateEsgKnowledgeFileContent(filename: string, content: string, language: string = 'zh') {
  return esgQaKnowledgeApi.updateKnowledgeFileContent(filename, content, language);
}

export function deleteEsgKnowledgeFile(filename: string, language: string = 'zh') {
  return esgQaKnowledgeApi.deleteKnowledgeFile(filename, language);
}

export function updateEsgKnowledgeFileMetadata(
  filename: string,
  metadata: { topic_id?: string | null; category_label?: string | null; topic_label?: string | null },
  language: string = 'zh',
) {
  return esgQaKnowledgeApi.updateKnowledgeFileMetadata(filename, metadata, language);
}

export function uploadEsgKnowledgeFileWithTopic(
  opts: Parameters<typeof esgQaKnowledgeApi.uploadKnowledgeFileWithTopic>[0],
) {
  return esgQaKnowledgeApi.uploadKnowledgeFileWithTopic(opts);
}

export function saveEsgTopicMergedCsv(
  topicId: string,
  payload: SaveTopicCsvMergedPayload,
  language: string = 'zh',
) {
  return esgQaKnowledgeApi.saveTopicMergedCsv(topicId, payload, language);
}

export function parseEsgQaCsvText(text: string) {
  return esgQaKnowledgeApi.parseQaCsvText(text);
}
