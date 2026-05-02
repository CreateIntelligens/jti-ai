import { useCallback, type KeyboardEvent } from 'react';

export function useEnterToSubmit(handler: () => void): (event: KeyboardEvent) => void {
  return useCallback((event: KeyboardEvent) => {
    if (event.nativeEvent.isComposing || event.keyCode === 229) return;
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handler();
    }
  }, [handler]);
}
