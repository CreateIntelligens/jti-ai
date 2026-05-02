import { useEffect, type RefObject } from 'react';

export function useFocusOnOpen(
  ref: RefObject<HTMLTextAreaElement | null>,
  isOpen: boolean,
): void {
  useEffect(() => {
    if (!isOpen) return;
    const textarea = ref.current;
    if (!textarea) return;
    textarea.focus();
    const end = textarea.value.length;
    textarea.setSelectionRange(end, end);
  }, [isOpen, ref]);
}
