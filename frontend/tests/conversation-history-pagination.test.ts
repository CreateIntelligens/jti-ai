import { describe, expect, it } from 'vitest';

import { resolveHistoryPageJump } from '../src/utils/conversationHistoryPagination';

describe('resolveHistoryPageJump', () => {
  it('keeps valid page jumps inside the available page range', () => {
    expect(resolveHistoryPageJump('42', 104, 7)).toBe(42);
  });

  it('clamps oversized page jumps to the last page', () => {
    expect(resolveHistoryPageJump('999', 104, 7)).toBe(104);
  });

  it('keeps the current page for blank or invalid page jumps', () => {
    expect(resolveHistoryPageJump('', 104, 7)).toBe(7);
    expect(resolveHistoryPageJump('abc', 104, 7)).toBe(7);
  });
});
