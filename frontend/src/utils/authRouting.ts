import type { LoginResponse, UserProfile } from '../services/api';

export function isAdminRole(role?: string | null): boolean {
  return role === 'admin' || role === 'super_admin';
}

export function getProfileRedirectPath(profile: Pick<UserProfile, 'app'>): string {
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
