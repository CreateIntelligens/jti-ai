import { expect, it } from 'vitest';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import HciotTopicGrid from '../../src/components/hciot/HciotTopicGrid';
import type { HciotTopic } from '../../src/config/hciotTopics';

it('renders a second-level question list for the selected topic', () => {
  const topics: HciotTopic[] = [
    {
      id: 'prp',
      label: 'PRP',
      questions: ['PRP 治療會痛嗎？', 'PRP 注射後多久會見效？'],
    },
  ];
  const html = renderToStaticMarkup(
    <HciotTopicGrid
      topics={topics}
      disabled={false}
      onSelect={() => {}}
      onSelectQuestion={() => {}}
      selectedTopicId="prp"
    />,
  );

  expect(html).toMatch(/PRP 治療會痛嗎？/);
});
