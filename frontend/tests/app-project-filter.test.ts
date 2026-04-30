import { describe, expect, it } from 'vitest';

import { filterStoresByProject, getProjectFilterOptions } from '../src/hooks/useAppChat';
import type { Store } from '../src/types';

describe('generic app project filtering', () => {
  it('does not classify managed local stores under the first Gemini key', () => {
    const stores: Store[] = [
      { name: '__jti__', display_name: 'JTI 中文', managed_app: 'jti', managed_language: 'zh', key_index: null },
      { name: '__hciot__', display_name: 'HCIoT 中文', managed_app: 'hciot', managed_language: 'zh', key_index: null },
    ];

    expect(getProjectFilterOptions(['POC1', 'POC2'], stores)).toEqual([]);
    expect(filterStoresByProject(stores, 'key:0')).toEqual(stores);
  });
});
