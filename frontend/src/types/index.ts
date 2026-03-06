export interface Store {
  name: string;
  display_name?: string;
  file_count?: number;
  created_at?: string;
  managed_app?: CmsAppTarget | null;
  managed_language?: KnowledgeLanguage | null;
  key_index?: number;
}

export type CmsAppTarget = 'jti' | 'hciot';
export type KnowledgeLanguage = 'zh' | 'en';

export type KnowledgeTarget =
  | {
      id: string;
      kind: 'store';
      label: string;
      storeName: string;
      managedApp?: CmsAppTarget | null;
      managedLanguage?: KnowledgeLanguage | null;
    }
  | {
      id: string;
      kind: 'app';
      label: string;
      appTarget: CmsAppTarget;
      language: KnowledgeLanguage;
    };

export interface FileItem {
  name: string;
  display_name?: string;
  size?: number;
  created_at?: string;
}

export interface Message {
  role: 'user' | 'model';
  text?: string;
  loading?: boolean;
  error?: boolean;
  turnNumber?: number;
  citations?: Array<{ title: string; uri: string }>;
}

export interface ChatResponse {
  answer: string;
  prompt_applied?: boolean;
  turn_number?: number;
  citations?: Array<{ title: string; uri: string }>;
}

export interface StartChatResponse {
  prompt_applied?: boolean;
  session_id?: string;
}
