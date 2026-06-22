export interface AppUpdateNotice {
  currentVersion: string;
  latestVersion: string;
}

type EnvLike = Record<string, string | undefined>;
type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

interface RuntimeVersionManifest {
  version?: unknown;
}

interface FetchAppUpdateNoticeOptions {
  appVersion?: string;
  env?: EnvLike;
  fetcher?: FetchLike;
  manifestUrl?: string;
}

function trimValue(value: string | undefined): string {
  return (value || '').trim();
}

function bundledAppVersion(): string {
  return typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : '';
}

function parseVersionParts(version: string): number[] | null {
  const normalized = version.replace(/^v/i, '').split(/[+-]/)[0];
  if (!/^\d+(?:\.\d+)*$/.test(normalized)) return null;
  return normalized.split('.').map((part) => Number(part));
}

function isLatestVersionNewer(currentVersion: string, latestVersion: string): boolean {
  const currentParts = parseVersionParts(currentVersion);
  const latestParts = parseVersionParts(latestVersion);

  if (!currentParts || !latestParts) {
    return latestVersion !== currentVersion;
  }

  const length = Math.max(currentParts.length, latestParts.length);
  for (let i = 0; i < length; i += 1) {
    const current = currentParts[i] ?? 0;
    const latest = latestParts[i] ?? 0;
    if (latest > current) return true;
    if (latest < current) return false;
  }
  return false;
}

function getCurrentVersion(env: EnvLike, appVersion?: string): string {
  return (
    trimValue(appVersion)
    || trimValue(env.VITE_APP_VERSION)
    || trimValue(bundledAppVersion())
  );
}

function getManifestUrl(env: EnvLike, manifestUrl?: string): string {
  const configuredUrl = trimValue(manifestUrl) || trimValue(env.VITE_VERSION_MANIFEST_URL);
  if (configuredUrl) return configuredUrl;

  const baseUrl = trimValue(env.BASE_URL) || '/';
  return `${baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`}version.json`;
}

function readManifestVersion(manifest: RuntimeVersionManifest): string {
  return typeof manifest.version === 'string' ? manifest.version : '';
}

export function getAppUpdateNotice(
  env: EnvLike = import.meta.env,
  latestVersionOverride?: string,
  appVersion?: string,
): AppUpdateNotice | null {
  const currentVersion = getCurrentVersion(env, appVersion);
  const latestVersion = trimValue(latestVersionOverride) || trimValue(env.VITE_LATEST_APP_VERSION);

  if (!currentVersion || !latestVersion) return null;
  if (!isLatestVersionNewer(currentVersion, latestVersion)) return null;

  return { currentVersion, latestVersion };
}

export async function fetchAppUpdateNotice({
  appVersion,
  env = import.meta.env,
  fetcher = globalThis.fetch?.bind(globalThis),
  manifestUrl,
}: FetchAppUpdateNoticeOptions = {}): Promise<AppUpdateNotice | null> {
  const envNotice = getAppUpdateNotice(env, undefined, appVersion);
  if (envNotice) return envNotice;
  if (!fetcher) return null;

  try {
    const response = await fetcher(getManifestUrl(env, manifestUrl), { cache: 'no-store' });
    if (!response.ok) return null;

    const latestVersion = readManifestVersion(await response.json() as RuntimeVersionManifest);
    return getAppUpdateNotice(env, latestVersion, appVersion);
  } catch {
    return null;
  }
}
