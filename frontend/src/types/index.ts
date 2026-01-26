export interface Store {
  name: string;
  display_name?: string;
  file_count?: number;
  created_at?: string;
}

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
}

export interface ChatResponse {
  answer: string;
  prompt_applied?: boolean;
}

export interface StartChatResponse {
  prompt_applied?: boolean;
}
