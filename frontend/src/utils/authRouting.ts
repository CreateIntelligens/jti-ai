import type { LoginResponse, UserProfile } from '../services/api';

export function isAdminRole(role?: string | null): boolean {
  return role === 'admin' || role === 'super_admin';
}

export function isGeneralUserScope(profile: Pick<UserProfile, 'app' | 'store_name' | 'role'>): boolean {
  if (isAdminRole(profile.role)) return false;
  if (profile.store_name) return true;
  if (profile.app === 'general') return true;
  return Boolean(profile.app?.startsWith('key_name:'));
}

export function getProfileRedirectPath(profile: Pick<UserProfile, 'app' | 'store_name' | 'role'>): string {
  if (isGeneralUserScope(profile)) return '/';
  if (profile.app === 'hciot') return '/hciot';
  if (profile.app === 'jti') return '/jti';
  return '/login';
}

export function getLoginRedirectPath(profile: Pick<LoginResponse, 'role' | 'app'>): string {
  if (isAdminRole(profile.role)) return '/';
  if (profile.role === 'user' && profile.app === 'hciot') return '/hciot';
  if (profile.role === 'user' && profile.app === 'jti') return '/jti';
  return '/';
}
