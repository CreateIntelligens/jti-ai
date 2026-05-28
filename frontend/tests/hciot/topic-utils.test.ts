import { describe, expect, it } from 'vitest';

import { normalizeLabel } from '../../src/components/_shared/qaKnowledgeWorkspace/topicUtils';

describe('normalizeLabel', () => {
  it('returns null for empty or whitespace-only input', () => {
    expect(normalizeLabel('')).toBeNull();
    expect(normalizeLabel('   ')).toBeNull();
  });

  it('returns the trimmed label when non-empty', () => {
    expect(normalizeLabel(' 骨科 ')).toBe('骨科');
    expect(normalizeLabel('Orthopedics')).toBe('Orthopedics');
  });
});
