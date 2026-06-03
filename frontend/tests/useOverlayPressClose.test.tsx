import { cleanup, fireEvent, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useOverlayPressClose } from '../src/hooks/useOverlayPressClose';

afterEach(() => {
  cleanup();
});

function TestDialog({ onClose }: { onClose: () => void }) {
  const overlayPressClose = useOverlayPressClose(onClose);

  return (
    <div data-testid="overlay" {...overlayPressClose}>
      <div data-testid="dialog">Dialog body</div>
    </div>
  );
}

describe('useOverlayPressClose', () => {
  it('does not close when a press starts inside and ends on the overlay', () => {
    const onClose = vi.fn();
    const { getByTestId } = render(<TestDialog onClose={onClose} />);

    fireEvent.mouseDown(getByTestId('dialog'));
    fireEvent.mouseUp(getByTestId('overlay'));

    expect(onClose).not.toHaveBeenCalled();
  });

  it('does not close when a press starts on the overlay and ends inside', () => {
    const onClose = vi.fn();
    const { getByTestId } = render(<TestDialog onClose={onClose} />);

    fireEvent.mouseDown(getByTestId('overlay'));
    fireEvent.mouseUp(getByTestId('dialog'));

    expect(onClose).not.toHaveBeenCalled();
  });

  it('closes when a press starts and ends on the overlay', () => {
    const onClose = vi.fn();
    const { getByTestId } = render(<TestDialog onClose={onClose} />);
    const overlay = getByTestId('overlay');

    fireEvent.mouseDown(overlay);
    fireEvent.mouseUp(overlay);

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
