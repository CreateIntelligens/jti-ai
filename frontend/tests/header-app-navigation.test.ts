import { describe, expect, it } from 'vitest';

import { buildAppNavOptions } from '../src/components/Header';

describe('header app navigation', () => {
  it('keeps the general entry and filters unavailable sub-apps', () => {
    const options = buildAppNavOptions((page) => page === 'home' || page === 'hciot');

    expect(options).toEqual([
      { value: '/', label: 'ai360 km 通用知識庫' },
      { value: '/hciot', label: 'HCIoT 衛教助手' },
    ]);
  });
});
