import { describe, expect, it } from 'vitest';

import { sortByLabel } from '../../src/components/hciot/knowledgeWorkspace/topicUtils';

describe('sortByLabel', () => {
  it('places common questions first', () => {
    const sorted = ['PRP 治療', '退化性膝關節炎', '常見問題'].sort(sortByLabel);

    expect(sorted).toEqual(['常見問題', 'PRP 治療', '退化性膝關節炎']);
  });
});
