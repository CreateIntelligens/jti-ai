import { describe, expect, it } from 'vitest';

import { filterStoresByProject, getProjectFilterOptions } from '../src/hooks/useAppChat';
import type { Store } from '../src/types';

describe('generic app project filtering', () => {
  it('shows only stores registered under the selected project key', () => {
    const stores: Store[] = [
      { name: '__jti__', display_name: 'JTI 中文', managed_app: 'jti', managed_language: 'zh', key_index: 2 },
      { name: '__hciot__', display_name: 'HCIoT 中文', managed_app: 'hciot', managed_language: 'zh', key_index: 3 },
      { name: 'store_poc1', display_name: 'POC1 KB', key_index: 0 },
      { name: 'store_unassigned', display_name: 'Unassigned KB', key_index: null },
    ];

    expect(getProjectFilterOptions(['POC1', 'POC2', 'JTI傑太日煙', '護聯HCIOT'], stores)).toEqual([
      { value: 'all', label: '全部專案' },
      { value: 'key:0', label: 'POC1' },
      { value: 'key:1', label: 'POC2' },
      { value: 'key:2', label: 'JTI傑太日煙' },
      { value: 'key:3', label: '護聯HCIOT' },
    ]);
    expect(filterStoresByProject(stores, 'key:0')).toEqual([stores[2]]);
    expect(filterStoresByProject(stores, 'key:2')).toEqual([stores[0]]);
    expect(filterStoresByProject(stores, 'key:3')).toEqual([stores[1]]);
    expect(filterStoresByProject(stores, 'all')).toEqual(stores);
  });
});
