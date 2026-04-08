export function normalizeImageId(raw?: string): string | null {
  if (!raw) return null;
  const filename = raw.split('/').pop() || '';
  const dotIdx = filename.lastIndexOf('.');
  return (dotIdx > 0 ? filename.slice(0, dotIdx) : filename) || null;
}

export function getHciotImageUrl(imageId?: string): string | null {
  const normalized = normalizeImageId(imageId);
  if (!normalized) return null;
  return `/api/hciot/images/${encodeURIComponent(normalized)}`;
}
