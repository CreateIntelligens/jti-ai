import { describe, expect, it } from 'vitest';

import { filterStoresByProject, getProjectFilterOptions } from '../src/hooks/useAppChat';
import type { Store } from '../src/types';

describe('generic app project filtering', () => {
  it('shows only stores registered under the selected project key', () => {
    const keyNames = ['POC1', 'POC2', 'JTI傑太日煙', '護聯HCIOT'];
    const stores: Store[] = [
      { name: '__jti__', display_name: 'JTI 中文', managed_app: 'jti', managed_language: 'zh', key_index: 2 },
      { name: '__hciot__', display_name: 'HCIoT 中文', managed_app: 'hciot', managed_language: 'zh', key_index: 3 },
      { name: 'store_poc1', display_name: 'POC1 KB', key_index: 0 },
      { name: 'store_unassigned', display_name: 'Unassigned KB', key_index: null },
    ];

    expect(getProjectFilterOptions(keyNames, stores)).toEqual([
      { value: 'all', label: '全部專案' },
      { value: 'key_name:POC1', label: 'POC1' },
      { value: 'key_name:POC2', label: 'POC2' },
      { value: 'key_name:JTI%E5%82%91%E5%A4%AA%E6%97%A5%E7%85%99', label: 'JTI傑太日煙' },
      { value: 'key_name:%E8%AD%B7%E8%81%AFHCIOT', label: '護聯HCIOT' },
    ]);
    expect(filterStoresByProject(stores, 'key_name:POC1', keyNames)).toEqual([stores[2]]);
    expect(filterStoresByProject(stores, 'key_name:JTI%E5%82%91%E5%A4%AA%E6%97%A5%E7%85%99', keyNames)).toEqual([stores[0]]);
    expect(filterStoresByProject(stores, 'key_name:%E8%AD%B7%E8%81%AFHCIOT', keyNames)).toEqual([stores[1]]);
    expect(filterStoresByProject(stores, 'key:0', keyNames)).toEqual(stores);
    expect(filterStoresByProject(stores, 'all')).toEqual(stores);
  });
});
