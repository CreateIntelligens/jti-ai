// Back-compat re-exports. Canonical helpers now live in utils/qaImage.ts; the
// shared workspace resolves image URLs through config.resolveImageUrl instead.
export { normalizeImageId, getQaImageUrl as getHciotImageUrl } from './qaImage';
