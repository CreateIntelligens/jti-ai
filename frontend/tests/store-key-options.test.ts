import { describe, expect, it } from 'vitest';

import { buildStoreKeyOptions } from '../src/components/StoreManagementModal';

describe('store creation key options', () => {
  it('uses readable project labels even when key names are blank or unavailable', () => {
    expect(buildStoreKeyOptions(['POC1', '', '  ', '護聯HCIOT'])).toEqual([
      { value: '0', label: 'POC1' },
      { value: '1', label: 'Key #2' },
      { value: '2', label: 'Key #3' },
      { value: '3', label: '護聯HCIOT' },
    ]);

    expect(buildStoreKeyOptions([])).toEqual([
      { value: '0', label: '全部專案' },
    ]);
  });
});
