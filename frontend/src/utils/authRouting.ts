import type { LoginResponse, UserProfile } from '../services/api';

export function isAdminRole(role?: string | null): boolean {
  return role === 'admin' || role === 'super_admin';
}

export function isGeneralUserScope(profile: Pick<UserProfile, 'scope' | 'store_name' | 'role'>): boolean {
  if (isAdminRole(profile.role)) return false;
  if (profile.store_name) return true;
  if (profile.scope === 'general') return true;
  return Boolean(profile.scope?.startsWith('key_name:'));
}

export function getProfileRedirectPath(profile: Pick<UserProfile, 'scope' | 'store_name' | 'role'>): string {
  if (isGeneralUserScope(profile)) return '/';
  switch (profile.scope) {
    case 'hciot':
      return '/hciot';
    case 'jti':
      return '/jti';
    default:
      return '/login';
  }
}

export function getLoginRedirectPath(profile: Pick<LoginResponse, 'role' | 'scope'>): string {
  if (isAdminRole(profile.role)) return '/';
  if (profile.role !== 'user') return '/';
  switch (profile.scope) {
    case 'hciot':
      return '/hciot';
    case 'jti':
      return '/jti';
    default:
      return '/';
  }
}
