import type { Store } from '../types';

const KEY_SCOPE_PREFIX = 'key_name:';

/**
 * Decode a `key_name:<encoded>` scope into its bare key name.
 * Returns null for non-key scopes (plain app scopes like `hciot`) or empty names.
 */
export function parseKeyScope(scope: string | null | undefined): string | null {
  if (!scope || !scope.startsWith(KEY_SCOPE_PREFIX)) return null;
  const encoded = scope.slice(KEY_SCOPE_PREFIX.length);
  try {
    return decodeURIComponent(encoded).trim() || null;
  } catch {
    return encoded.trim() || null;
  }
}

/** Encode a key name into a `key_name:<encoded>` scope value. */
export function formatKeyScope(name: string): string {
  return `${KEY_SCOPE_PREFIX}${encodeURIComponent(name)}`;
}

/**
 * Whether a store belongs to the given key name, falling back to the store's
 * positional key_index against `keyNames` when the store has no `key_name`.
 */
export function storeMatchesKeyName(store: Store, keyName: string, keyNames: string[] = []): boolean {
  const target = keyName.trim().toLowerCase();
  if (!target) return false;
  if (store.key_name) return store.key_name.trim().toLowerCase() === target;
  if (typeof store.key_index === 'number') {
    return (keyNames[store.key_index] || '').trim().toLowerCase() === target;
  }
  return false;
}
