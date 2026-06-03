import { useRef, type MouseEvent } from 'react';

export function useOverlayPressClose(onClose: () => void) {
  const overlayPressStartedRef = useRef(false);

  const onMouseDown = (event: MouseEvent<HTMLElement>) => {
    overlayPressStartedRef.current = event.target === event.currentTarget;
  };

  const onMouseUp = (event: MouseEvent<HTMLElement>) => {
    const shouldClose = overlayPressStartedRef.current && event.target === event.currentTarget;
    overlayPressStartedRef.current = false;

    if (shouldClose) {
      onClose();
    }
  };

  return { onMouseDown, onMouseUp };
}
