// Neutral QA-format topic model shared across sub-apps (hciot, general, esg…).
//
// Any app whose knowledge is authored in the QA/topic format (category → topic →
// questions, optionally with hidden questions and merged CSV) routes through the
// shared QA knowledge workspace and should depend on THESE types — not on any
// single app's namespace. hciot keeps `Hciot*`-named aliases for backward
// compatibility (see config/hciotTopics.ts and services/api/hciot.ts), but the
// canonical definitions live here so the shared layer never points "downward"
// into one consumer.

export type QaLanguage = 'zh' | 'en';

// Runtime/chat-facing topic: what the public topic grid renders.
export interface QaTopic {
  id: string;
  order?: number;
  label: string;
  questions: string[];
}

export interface QaCategory {
  id: string;
  order?: number;
  label: string;
  topics: QaTopic[];
}

// Admin-facing topic: superset of the runtime topic, adds editor-only fields
// (per-question hiding, category/topic visibility) used by the admin workspace.
export interface QaAdminTopic extends QaTopic {
  hidden_questions?: string[];
  hidden?: boolean;
}

export interface QaAdminCategory {
  id: string;
  order?: number;
  label: string;
  hidden?: boolean;
  topics: QaAdminTopic[];
}

export function normalizeQaLanguage(language?: string): QaLanguage {
  return typeof language === 'string' && language.trim().toLowerCase().startsWith('en')
    ? 'en'
    : 'zh';
}
