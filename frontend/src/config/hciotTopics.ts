// hciot consumes the neutral QA topic model; these names are kept as aliases so
// existing hciot code (and its `language` arg) need not change. The canonical
// definitions live in config/qaTopics.ts.
import type { QaLanguage, QaTopic, QaCategory } from './qaTopics';
import { normalizeQaLanguage } from './qaTopics';

export type HciotLanguage = QaLanguage;
export type HciotTopic = QaTopic;
export type HciotCategory = QaCategory;

export const HCIOT_DEFAULT_STORE_NAME = (
  (import.meta.env.VITE_HCIOT_STORE_NAME as string | undefined)?.trim() || 'hciot'
);

export const normalizeHciotLanguage = normalizeQaLanguage;
