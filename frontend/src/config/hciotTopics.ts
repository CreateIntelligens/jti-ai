export type HciotLanguage = 'zh' | 'en';

export interface HciotTopic {
  id: string;
  order?: number;
  label: string;
  questions: string[];
}

export interface HciotCategory {
  id: string;
  order?: number;
  label: string;
  topics: HciotTopic[];
}

export const HCIOT_DEFAULT_STORE_NAME = (
  (import.meta.env.VITE_HCIOT_STORE_NAME as string | undefined)?.trim() || 'hciot'
);

export function normalizeHciotLanguage(language?: string): HciotLanguage {
  return typeof language === 'string' && language.trim().toLowerCase().startsWith('en')
    ? 'en'
    : 'zh';
}
