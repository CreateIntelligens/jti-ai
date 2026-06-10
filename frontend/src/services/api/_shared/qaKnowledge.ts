import type { KnowledgeFile, KnowledgeFileContent } from '../../../types';
import { buildUrl, fetchAsAdmin, handleResponse, normLang } from '../base';

const JSON_HEADERS = { 'Content-Type': 'application/json' };

type QueryValue = string | number | boolean | null | undefined;
type KnowledgeMetadataPayload = {
  topic_id?: string | null;
  category_label?: string | null;
  topic_label?: string | null;
};
type ContentUpdateResponse = { message: string; synced: boolean; topic_synced: boolean };
type KnowledgeUploadResponse = QaKnowledgeFile & {
  synced: boolean;
  topic_synced: boolean;
  uploaded_count?: number;
  uploaded_files?: string[];
};

export type QaKnowledgeFile = KnowledgeFile;
export type QaKnowledgeFileContent = KnowledgeFileContent;

export interface QaKnowledgeUploadWithTopicOptions {
  language: string;
  file: File;
  categoryId?: string;
  topicId?: string;
  categoryLabel?: string;
  topicLabel?: string;
  hiddenQuestions?: string[];
}

export interface QaMergedCsvRow {
  index: string;
  q: string;
  a: string;
  img: string;
  url?: string;
  source_file?: string;
}

export interface QaMergedCsvResponse {
  rows: QaMergedCsvRow[];
  source_files: string[];
}

export interface QaPair {
  index?: string;
  q: string;
  a: string;
  img?: string;
  url?: string;
  display?: string;
}

export interface QaExtractJobResponse {
  job_id: string;
  status: 'pending' | 'running' | 'done' | 'failed';
  qa_pairs?: QaPair[];
  error?: string;
}

export interface QaImportResponse {
  imported_count: number;
  filename: string;
  topic_synced: boolean;
  skipped_all_duplicates?: boolean;
  topic_id?: string | null;
}

export interface SaveTopicCsvMergedPayload {
  files: Array<{ filename: string; content: string }>;
  delete_files?: string[];
  hidden_questions?: string[];
}

export interface QaKnowledgeApi {
  listKnowledgeFiles(language?: string): Promise<{ files: QaKnowledgeFile[] }>;
  getKnowledgeFileContent(filename: string, language?: string): Promise<QaKnowledgeFileContent>;
  downloadKnowledgeFile(filename: string, language?: string): void;
  updateKnowledgeFileContent(
    filename: string,
    content: string,
    language?: string,
  ): Promise<ContentUpdateResponse>;
  deleteKnowledgeFile(fileName: string, language?: string): Promise<void>;
  updateKnowledgeFileMetadata(
    filename: string,
    metadata: KnowledgeMetadataPayload,
    language?: string,
  ): Promise<QaKnowledgeFile & { topic_synced: boolean }>;
  uploadKnowledgeFileWithTopic(opts: QaKnowledgeUploadWithTopicOptions): Promise<KnowledgeUploadResponse>;
  getTopicMergedCsv(topicId: string, language?: string): Promise<QaMergedCsvResponse>;
  saveTopicMergedCsv(
    topicId: string,
    payload: SaveTopicCsvMergedPayload,
    language?: string,
  ): Promise<{ message: string; topic_synced: boolean }>;
  createQaExtractJob(
    language: string,
    source: { file: File } | { text: string },
    categoryId: string,
    topicId: string,
    categoryLabel: string,
    topicLabel: string,
  ): Promise<{ job_id: string; status: string }>;
  parseQaCsvText(text: string): Promise<{ parsed: boolean; qa_pairs: QaPair[] }>;
  getQaExtractJob(jobId: string): Promise<QaExtractJobResponse>;
  importQaExtractJob(
    jobId: string,
    language: string,
    qaPairs: QaPair[],
    hiddenQuestions?: string[],
  ): Promise<QaImportResponse>;
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

export function createQaKnowledgeApi(basePath: string): QaKnowledgeApi {
  const fetchJson = async <T>(
    path: string,
    options?: RequestInit,
    params?: Record<string, QueryValue>,
  ): Promise<T> => {
    const response = await fetchAsAdmin(buildUrl(`${basePath}${path}`, params), options);
    return handleResponse<T>(response);
  };

  return {
    listKnowledgeFiles(language: string = 'zh') {
      return fetchJson<{ files: QaKnowledgeFile[] }>('/files/', undefined, {
        language: normLang(language),
      });
    },

    getKnowledgeFileContent(filename: string, language: string = 'zh') {
      return fetchJson<QaKnowledgeFileContent>(
        `/files/${encodeURIComponent(filename)}/content`,
        undefined,
        { language: normLang(language) },
      );
    },

    downloadKnowledgeFile(filename: string, language: string = 'zh') {
      window.open(
        buildUrl(`${basePath}/files/${encodeURIComponent(filename)}/download`, {
          language: normLang(language),
        }),
        '_blank',
      );
    },

    updateKnowledgeFileContent(filename: string, content: string, language: string = 'zh') {
      return fetchJson<ContentUpdateResponse>(
        `/files/${encodeURIComponent(filename)}/content`,
        jsonRequest('PUT', { content }),
        { language: normLang(language) },
      );
    },

    async deleteKnowledgeFile(fileName: string, language: string = 'zh') {
      await fetchJson<void>(`/files/${encodeURIComponent(fileName)}`, {
        method: 'DELETE',
      }, {
        language: normLang(language),
      });
    },

    updateKnowledgeFileMetadata(filename, metadata, language: string = 'zh') {
      return fetchJson<QaKnowledgeFile & { topic_synced: boolean }>(
        `/files/${encodeURIComponent(filename)}/metadata`,
        jsonRequest('PUT', metadata),
        { language: normLang(language) },
      );
    },

    uploadKnowledgeFileWithTopic(opts) {
      const formData = new FormData();
      formData.append('file', opts.file);
      appendOptionalFormValue(formData, 'category_id', opts.categoryId);
      appendOptionalFormValue(formData, 'topic_id', opts.topicId);
      appendOptionalFormValue(formData, 'category_label', opts.categoryLabel);
      appendOptionalFormValue(formData, 'topic_label', opts.topicLabel);
      if (opts.hiddenQuestions !== undefined) {
        formData.append('hidden_questions', JSON.stringify(opts.hiddenQuestions));
      }

      return fetchJson<KnowledgeUploadResponse>('/upload/', {
        method: 'POST',
        body: formData,
      }, {
        language: normLang(opts.language),
      });
    },

    getTopicMergedCsv(topicId: string, language: string = 'zh') {
      return fetchJson<QaMergedCsvResponse>('/topic-csv-merged', undefined, {
        topic_id: topicId,
        language: normLang(language),
      });
    },

    saveTopicMergedCsv(topicId: string, payload: SaveTopicCsvMergedPayload, language: string = 'zh') {
      return fetchJson<{ message: string; topic_synced: boolean }>(
        '/topic-csv-merged',
        jsonRequest('PUT', payload),
        { topic_id: topicId, language: normLang(language) },
      );
    },

    createQaExtractJob(language, source, categoryId, topicId, categoryLabel, topicLabel) {
      const formData = new FormData();
      if ('file' in source) {
        formData.append('file', source.file);
      } else {
        formData.append('text_input', source.text);
      }
      formData.append('category_id', categoryId);
      formData.append('topic_id', topicId);
      formData.append('category_label', categoryLabel);
      formData.append('topic_label', topicLabel);
      formData.append('language', normLang(language));

      return fetchJson<{ job_id: string; status: string }>('/qa-extract', {
        method: 'POST',
        body: formData,
      });
    },

    parseQaCsvText(text: string) {
      return fetchJson<{ parsed: boolean; qa_pairs: QaPair[] }>('/qa-parse-csv', {
        method: 'POST',
        headers: JSON_HEADERS,
        body: JSON.stringify({ text }),
      });
    },

    getQaExtractJob(jobId: string) {
      return fetchJson<QaExtractJobResponse>(`/qa-extract/${encodeURIComponent(jobId)}`);
    },

    importQaExtractJob(jobId, language, qaPairs, hiddenQuestions) {
      return fetchJson<QaImportResponse>(
        `/qa-extract/${encodeURIComponent(jobId)}/import`,
        {
          method: 'POST',
          headers: JSON_HEADERS,
          body: JSON.stringify({
            qa_pairs: qaPairs,
            ...(hiddenQuestions !== undefined ? { hidden_questions: hiddenQuestions } : {}),
          }),
        },
        { language: normLang(language) },
      );
    },
  };
}
