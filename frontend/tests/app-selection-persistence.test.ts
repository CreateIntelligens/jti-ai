import { describe, expect, it } from 'vitest';

import { resolvePersistedKnowledgeTargetId } from '../src/hooks/useAppChat';
import type { Store } from '../src/types';

describe('generic app knowledge selection persistence', () => {
  it('restores the persisted store from the full store list', () => {
    const stores: Store[] = [
      { name: 'store_a', display_name: 'Store A', key_index: 0 },
      { name: 'store_b', display_name: 'Store B', key_index: 1 },
    ];

    expect(resolvePersistedKnowledgeTargetId(stores, 'store_b')).toBe('store_b');
  });
});
