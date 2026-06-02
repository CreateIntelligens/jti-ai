import { useEffect, useState } from 'react';
import * as api from '../services/api';

interface UseCurrentUserProfileOptions {
  enabled?: boolean;
  onError?: (error: unknown) => void;
}

export function useCurrentUserProfile({
  enabled = true,
  onError,
}: UseCurrentUserProfileOptions = {}) {
  const [profile, setProfile] = useState<api.UserProfile | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return undefined;
    }

    let active = true;
    setLoading(true);
    setError(null);

    api.getMe()
      .then((nextProfile) => {
        if (active) {
          setProfile(nextProfile);
        }
      })
      .catch((nextError: unknown) => {
        if (active) {
          setError(nextError);
          onError?.(nextError);
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [enabled, onError]);

  return { profile, setProfile, loading, error };
}

