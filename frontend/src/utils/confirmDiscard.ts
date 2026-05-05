type DiscardAction = 'close' | 'cancel' | 'switch' | 'discard';

const MESSAGES: Record<DiscardAction, string> = {
  close: '有未儲存的變更，確定關閉？',
  cancel: '有未儲存的變更，確定要取消嗎？',
  switch: '有未儲存的變更，確定切換？',
  discard: '放棄未儲存的變更？',
};

export function confirmDiscard(action: DiscardAction = 'close'): boolean {
  return window.confirm(MESSAGES[action]);
}
