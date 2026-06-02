import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import * as api from '../services/api';

export function useLogoutRedirect(
  onLogout?: () => void,
  onError?: (error: unknown) => void,
) {
  const navigate = useNavigate();

  return useCallback(async () => {
    try {
      await api.logout();
    } catch (error: unknown) {
      onError?.(error);
    }

    onLogout?.();
    navigate('/login');
  }, [navigate, onError, onLogout]);
}
