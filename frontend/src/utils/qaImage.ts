// Neutral QA-image helpers shared across sub-apps. Each host app owns its own
// image URL scheme (hciot vs. per-store general/esg), so URL resolution is
// supplied by the workspace config's `resolveImageUrl` callback rather than
// hardcoded here. `getQaImageUrl` provides the hciot-path default used when
// `resolveImageUrl` is not supplied by the host app.

export function normalizeImageId(raw?: string): string | null {
  if (!raw) return null;
  const filename = raw.split('/').pop() || '';
  const dotIdx = filename.lastIndexOf('.');
  return (dotIdx > 0 ? filename.slice(0, dotIdx) : filename) || null;
}

// Default image URL resolver: uses the hciot image API path.
// Host apps with a different image URL scheme supply their own via QaWorkspaceConfig.resolveImageUrl.
export function getQaImageUrl(imageId?: string): string | null {
  const normalized = normalizeImageId(imageId);
  if (!normalized) return null;
  return `/api/hciot/images/${encodeURIComponent(normalized)}`;
}
