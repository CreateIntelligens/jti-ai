import { useEffect, type RefObject } from 'react';

export function useScrollToBottom(ref: RefObject<HTMLElement | null>, deps: unknown[]) {
  useEffect(() => {
    ref.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, deps);
}
