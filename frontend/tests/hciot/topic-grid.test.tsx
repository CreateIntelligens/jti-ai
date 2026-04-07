import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import HciotTopicGrid from '../../src/components/hciot/HciotTopicGrid';

test('renders a second-level question list for the selected topic', () => {
  const topics = [
    {
      id: 'prp',
      icon: '🩸',
      accent: '#8f5cf7',
      labels: { zh: 'PRP', en: 'PRP Therapy' },
      summaries: {
        zh: '了解適應症、術後照護與常見疑問。',
        en: 'Learn indications, post-procedure care, and common questions.',
      },
      questions: {
        zh: ['PRP 治療會痛嗎？', 'PRP 注射後多久會見效？'],
        en: ['PRP 治療會痛嗎？', 'PRP 注射後多久會見效？'],
      },
    },
  ];
  const html = renderToStaticMarkup(
    <HciotTopicGrid
      topics={topics}
      language="zh"
      disabled={false}
      onSelect={() => {}}
      onSelectQuestion={() => {}}
      selectedTopicId="prp"
      heading="常用衛教主題"
      subheading="先選主題，再選問題"
      questionHeading="PRP 常見問題"
    />,
  );

  assert.match(html, /PRP 治療會痛嗎？/);
});
