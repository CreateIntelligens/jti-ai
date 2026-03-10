export function getHciotImageUrl(imageId?: string): string | null {
  const normalized = imageId?.trim();
  if (!normalized) return null;
  return `/api/hciot/images/${encodeURIComponent(normalized)}`;
}
