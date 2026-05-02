export const PROJECT_COLORS = ['#0f766e', '#7c3aed', '#d97706', '#0284c7', '#dc2626', '#059669'];

export function getStoreIcon(app: string): string {
  const normalizedApp = app.trim().toLowerCase();
  if (normalizedApp === 'jti') return '🏢';
  if (normalizedApp === 'hciot') return '🏥';
  return '📁';
}
