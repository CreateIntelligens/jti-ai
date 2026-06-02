import type { Store } from '../types';

export const PROJECT_COLORS = ['#0f766e', '#7c3aed', '#d97706', '#0284c7', '#dc2626', '#059669'];

type ManagedKnowledgeStoreFields = Pick<Store, 'managed_app' | 'managed_language'> & {
  managed_app: NonNullable<Store['managed_app']>;
  managed_language: NonNullable<Store['managed_language']>;
};

export function getStoreIcon(app: string): string {
  const normalizedApp = app.trim().toLowerCase();
  if (normalizedApp === 'jti') return '🏢';
  if (normalizedApp === 'hciot') return '🏥';
  return '📁';
}

export function isManagedKnowledgeStore(
  store: Pick<Store, 'managed_app' | 'managed_language'> | null | undefined,
): store is ManagedKnowledgeStoreFields {
  return Boolean(store?.managed_app && store?.managed_language);
}
