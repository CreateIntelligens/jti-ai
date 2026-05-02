import { useCallback, useEffect, useRef, useState } from 'react';

export function useTransientStatus(durationMs: number = 3000): [string | null, (msg: string) => void] {
  const [status, setStatus] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);

  const clearTimer = useCallback(() => {
    if (timerRef.current === null) return;
    window.clearTimeout(timerRef.current);
    timerRef.current = null;
  }, []);

  const showStatus = useCallback((msg: string) => {
    clearTimer();
    setStatus(msg);
    timerRef.current = window.setTimeout(() => {
      setStatus(null);
      timerRef.current = null;
    }, durationMs);
  }, [clearTimer, durationMs]);

  useEffect(() => clearTimer, [clearTimer]);

  return [status, showStatus];
}
