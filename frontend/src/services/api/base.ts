export const API_BASE = '/api';

const STORAGE_KEYS = 'userGeminiApiKeys';
const STORAGE_ACTIVE = 'activeGeminiApiKey';

export function getUserApiKey(): string | null {
  const activeName = localStorage.getItem(STORAGE_ACTIVE) || 'system';
  if (activeName === 'system') return null;
  try {
    const keys: { name: string; key: string }[] = JSON.parse(localStorage.getItem(STORAGE_KEYS) || '[]');
    const found = keys.find(k => k.name === activeName);
    return found?.key || null;
  } catch {
    return null;
  }
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
