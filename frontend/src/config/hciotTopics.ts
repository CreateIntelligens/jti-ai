export type HciotLanguage = 'zh' | 'en';

export interface HciotTopic {
  id: string;
  order?: number;
  labels: Record<HciotLanguage, string>;
  questions: Record<HciotLanguage, string[]>;
}

export interface HciotCategory {
  id: string;
  order?: number;
  labels: Record<HciotLanguage, string>;
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
