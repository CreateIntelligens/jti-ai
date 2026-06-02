export const API_BASE = '/api';

export const STORAGE_KEYS = 'userGeminiApiKeys';
export const STORAGE_ACTIVE = 'activeGeminiApiKey';

export function getUserApiKey(): string | null {
  const activeName = (localStorage.getItem(STORAGE_ACTIVE) || 'system').trim();
  if (activeName === 'system') return null;
  try {
    const keys: { name: string; key: string }[] = JSON.parse(localStorage.getItem(STORAGE_KEYS) || '[]');
    const found = keys.find(k => (k.name || '').trim() === activeName);
    return (found?.key || '').trim() || null;
  } catch {
    return null;
  }
}

export function getUserGeminiApiKey(): string | null {
  return getUserApiKey();
}

export async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || response.statusText);
  }
  return response.json();
}

export async function fetchWithApiKey(url: string, options: RequestInit = {}): Promise<Response> {
  const apiKey = getUserApiKey();
  const headers = new Headers(options.headers || {});
  if (apiKey) {
    headers.set('API-Token', apiKey);
  }
  return fetch(url, { ...options, headers });
}

export async function fetchWithUserGeminiKey(url: string, options: RequestInit = {}): Promise<Response> {
  const apiKey = getUserGeminiApiKey();
  const headers = new Headers(options.headers || {});
  if (apiKey) {
    headers.set('X-Gemini-API-Key', apiKey);
  }
  return fetch(url, { ...options, headers });
}

export async function fetchAsAdmin(url: string, options: RequestInit = {}): Promise<Response> {
  return fetch(url, options);
}

export function normLang(language: string): string {
  return language.toLowerCase().startsWith('en') ? 'en' : 'zh';
}

export function buildUrl(path: string, params?: Record<string, string | number | boolean | null | undefined>): string {
  if (!params) return path;
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value != null) searchParams.set(key, String(value));
  });
  const query = searchParams.toString();
  return query ? `${path}${path.includes('?') ? '&' : '?'}${query}` : path;
}
