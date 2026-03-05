export const API_BASE = '/api';

const STORAGE_KEYS = 'userGeminiApiKeys';
const STORAGE_ACTIVE = 'activeGeminiApiKey';

export function getUserApiKey(): string | null {
  const activeName = (localStorage.getItem(STORAGE_ACTIVE) || 'system').trim();
  if (activeName === 'system') return null;
  try {
    const keys: { name: string; key: string }[] = JSON.parse(localStorage.getItem(STORAGE_KEYS) || '[]');
    const found = keys.find(k => (k.name || '').trim() === activeName);
    const trimmedKey = (found?.key || '').trim();
    return trimmedKey || null;
  } catch {
    return null;
  }
}

export function getUserGeminiApiKey(): string | null {
  return getUserApiKey();
}

function isSameOriginApiRequest(url: string): boolean {
  try {
    const resolved = new URL(url, window.location.origin);
    return resolved.origin === window.location.origin;
  } catch {
    return false;
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

  const response = await fetch(url, { ...options, headers });
  if (!apiKey || response.status !== 401 || !isSameOriginApiRequest(url)) {
    return response;
  }

  const errorText = await response.clone().text();
  const shouldFallback =
    errorText.includes('Invalid API token') ||
    errorText.includes('Missing Authorization') ||
    errorText.includes('Missing Authorization Bearer token or API-Token header');

  if (!shouldFallback) {
    return response;
  }

  const fallbackHeaders = new Headers(options.headers || {});
  fallbackHeaders.delete('API-Token');
  fallbackHeaders.delete('api-token');
  fallbackHeaders.delete('API-Key');
  fallbackHeaders.delete('api-key');

  return fetch(url, { ...options, headers: fallbackHeaders });
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
