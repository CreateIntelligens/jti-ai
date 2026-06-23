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

// 常見 FastAPI/pydantic 驗證 type → 中文。msg 缺漏時的 fallback。
const VALIDATION_TYPE_MESSAGES: Record<string, string> = {
  'missing': '為必填',
  'value_error.missing': '為必填',
  'string_too_short': '長度不足',
  'value_error.any_str.min_length': '長度不足',
  'string_too_long': '長度超過上限',
  'value_error.email': 'Email 格式不正確',
};

/**
 * 把單筆 FastAPI 422 驗證錯誤格式化成「欄位: 說明」。
 * loc 通常是 ["body", "field"] 之類；跳過 body/query/path 等位置前綴只留欄位名。
 */
function formatValidationError(item: unknown): string {
  if (!item || typeof item !== 'object') return '';
  const { loc, msg, type } = item as { loc?: unknown; msg?: unknown; type?: unknown };
  const fieldParts = Array.isArray(loc)
    ? loc.filter((p) => typeof p === 'string' && !['body', 'query', 'path', 'header'].includes(p))
    : [];
  const field = fieldParts.join('.');
  const reason =
    (typeof type === 'string' && VALIDATION_TYPE_MESSAGES[type]) ||
    (typeof msg === 'string' ? msg : '') ||
    '格式不正確';
  return field ? `${field}: ${reason}` : reason;
}

/**
 * 從錯誤 response 取出可讀訊息。
 * 優先解析 FastAPI 的 { detail: ... } 結構,避免把原始 JSON 字串直接丟給使用者。
 * 非 JSON 回應(blob 下載等)無法走 handleResponse 的端點，可在 !response.ok 時
 * 直接呼叫此函式取得一致的錯誤訊息。
 */
export async function extractErrorMessage(response: Response): Promise<string> {
  // 後端未啟動時 nginx 會回 502/503/504 + 一坨 HTML 錯誤頁；直接給友善訊息，
  // 不要把整段 <html>…</html> 丟到畫面上。
  if (response.status === 502 || response.status === 503 || response.status === 504) {
    return '伺服器暫時無法連線，請稍後再試（後端服務可能尚未啟動）。';
  }

  const raw = await response.text();
  if (raw) {
    try {
      const parsed = JSON.parse(raw);
      const detail = parsed?.detail;
      if (typeof detail === 'string') return detail;
      // FastAPI 驗證錯誤(422): detail 是 [{loc, msg, type}, ...]。
      // 帶上欄位名並合併多筆，避免只顯示無頭緒的英文 "field required"。
      if (Array.isArray(detail) && detail.length > 0) {
        const formatted = detail
          .map(formatValidationError)
          .filter(Boolean);
        if (formatted.length > 0) return formatted.join('；');
      }
      if (typeof parsed?.message === 'string') return parsed.message;
    } catch {
      // 非 JSON（例如 nginx/proxy 的 HTML 錯誤頁）：別把原始 HTML 丟給使用者。
      if (raw.trimStart().startsWith('<')) {
        return response.statusText || '伺服器發生錯誤，請稍後再試。';
      }
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
  // 帶上 session cookie：身份靠帳號登入的 cookie，X-Gemini-API-Key 只是使用者自帶的
  // Gemini key（非身份憑證）。少了 credentials 後端就收不到登入身份 → store 操作 403。
  return fetch(url, { ...options, headers, credentials: 'include' });
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
