import { useEffect, useRef } from 'react';

type EscHandler = (e: KeyboardEvent) => void;

const globalAny = globalThis as { __escKeyStack?: EscHandler[]; __escKeyBound?: boolean };
const stack: EscHandler[] = globalAny.__escKeyStack ?? (globalAny.__escKeyStack = []);

if (typeof window !== 'undefined' && !globalAny.__escKeyBound) {
  globalAny.__escKeyBound = true;
  window.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'Escape' && stack.length > 0) {
      stack[stack.length - 1](e);
    }
  });
}

export function useEscapeKey(handler: () => void, enabled = true) {
  const handlerRef = useRef(handler);
  useEffect(() => { handlerRef.current = handler; });

  useEffect(() => {
    if (!enabled) return;
    const escHandler: EscHandler = () => {
      handlerRef.current();
    };
    stack.push(escHandler);
    return () => {
      const idx = stack.indexOf(escHandler);
      if (idx !== -1) stack.splice(idx, 1);
    };
  }, [enabled]);
}
