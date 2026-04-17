import { describe, expect, it } from 'vitest';

import { buildLabels } from '../../src/components/hciot/knowledgeWorkspace/topicUtils';

describe('buildLabels', () => {
  it('returns null when either language label is missing', () => {
    expect(buildLabels('', '')).toBeNull();
    expect(buildLabels('骨科', '')).toBeNull();
    expect(buildLabels('', 'Orthopedics')).toBeNull();
  });

  it('returns exact trimmed bilingual labels when both are provided', () => {
    expect(buildLabels(' 骨科 ', ' Orthopedics ')).toEqual({
      zh: '骨科',
      en: 'Orthopedics',
    });
  });
});
