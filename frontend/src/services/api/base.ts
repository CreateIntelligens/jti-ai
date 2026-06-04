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
    throw new Error(await extractErrorMessage(response));
  }
  return response.json();
}

/**
 * 從錯誤 response 取出可讀訊息。
 * 優先解析 FastAPI 的 { detail: ... } 結構,避免把原始 JSON 字串直接丟給使用者。
 */
async function extractErrorMessage(response: Response): Promise<string> {
  const raw = await response.text();
  if (raw) {
    try {
      const parsed = JSON.parse(raw);
      const detail = parsed?.detail;
      if (typeof detail === 'string') return detail;
      // FastAPI 驗證錯誤: detail 是陣列
      if (Array.isArray(detail) && detail.length > 0) {
        const first = detail[0];
        if (typeof first?.msg === 'string') return first.msg;
      }
      if (typeof parsed?.message === 'string') return parsed.message;
    } catch {
      // 非 JSON,退回原始文字
      return raw;
    }
  }
  return response.statusText || '發生未知錯誤';
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
  // Admin 身份走 cookie-based session（login 時後端 set 的 httpOnly cookie）。
  // 必須帶 credentials:'include' 瀏覽器才會把 cookie 送出，否則後端收到匿名請求 → 403。
  // 與 auth.ts 各呼叫保持一致。
  return fetch(url, { ...options, credentials: 'include' });
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
