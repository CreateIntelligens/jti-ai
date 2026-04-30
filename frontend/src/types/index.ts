export interface Store {
  name: string;
  display_name?: string;
  file_count?: number;
  created_at?: string;
  managed_app?: AppTarget | null;
  managed_language?: KnowledgeLanguage | null;
  key_index?: number | null;
}

export type AppTarget = 'jti' | 'hciot';
export type KnowledgeLanguage = 'zh' | 'en';

export type KnowledgeTarget =
  | {
      id: string;
      kind: 'store';
      label: string;
      storeName: string;
      managedApp?: AppTarget | null;
      managedLanguage?: KnowledgeLanguage | null;
    }
  | {
      id: string;
      kind: 'app';
      label: string;
      appTarget: AppTarget;
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
  citations?: Array<{ title: string; uri: string; text?: string }>;
}

export type TtsState = 'pending' | 'ready' | 'error';

export interface ChatResponse {
  answer: string;
  prompt_applied?: boolean;
  turn_number?: number;
  citations?: Array<{ title: string; uri: string; text?: string }>;
  image_id?: string;
  tts_text?: string;
  tts_message_id?: string;
}

export interface StartChatResponse {
  prompt_applied?: boolean;
  session_id?: string;
  opening_message?: string;
}
