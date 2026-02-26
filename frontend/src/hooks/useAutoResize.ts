import { useEffect, type RefObject } from 'react';

export function useAutoResize(ref: RefObject<HTMLTextAreaElement | null>, value: string) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    const styles = window.getComputedStyle(el);
    const maxHeight = parseFloat(styles.maxHeight || '160');
    const nextHeight = Math.min(el.scrollHeight, maxHeight);
    el.style.height = `${nextHeight}px`;
    el.style.overflowY = el.scrollHeight > maxHeight ? 'auto' : 'hidden';
  }, [ref, value]);
}
