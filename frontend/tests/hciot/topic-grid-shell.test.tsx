import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';

import HciotTopicGrid from '../../src/components/hciot/HciotTopicGrid';

describe('HciotTopicGrid shell', () => {
  it('renders prototype-style category/topic buttons and supports expanding question lists', () => {
    const categories = [
      {
        id: 'ortho',
        labels: { zh: '骨科 + 復健科', en: 'Orthopedics + Rehab' },
        topics: [
          {
            id: 'prp',
            labels: { zh: 'PRP 治療', en: 'PRP Therapy' },
            questions: {
              zh: [
                'PRP 是什麼?',
                '一次療程需要幾針?',
                '打完 PRP 後多久可以運動?',
                '健保有給付嗎?',
                '打針當天可以洗澡嗎?',
                '哪些人不適合 PRP?',
                '多久需要回診?',
              ],
              en: [],
            },
          },
          {
            id: 'knee',
            labels: { zh: '退化性膝關節炎', en: 'Knee Osteoarthritis' },
            questions: { zh: ['哪些運動可以緩解?'], en: [] },
          },
        ],
      },
      {
        id: 'cardio',
        labels: { zh: '心血管內科', en: 'Cardiology' },
        topics: [],
      },
    ];

    render(
      <HciotTopicGrid
        topics={categories[0].topics}
        categories={categories}
        language="zh"
        disabled={false}
        onSelect={() => {}}
        onSelectQuestion={() => {}}
        onSelectCategory={() => {}}
        selectedTopicId="prp"
        selectedCategoryId="ortho"
        heading="常用衛教主題"
        subheading="先選主題，再選問題"
        questionHeading="PRP 治療 · 常見問題"
      />,
    );

    expect(screen.queryAllByRole('combobox')).toHaveLength(0);
    expect(screen.getByRole('button', { name: /骨科 \+ 復健科/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /PRP 治療/ })).toBeTruthy();
    expect(screen.getByText('7')).toBeTruthy();

    expect(screen.getByText('PRP 是什麼?')).toBeTruthy();
    expect(screen.getByText('打針當天可以洗澡嗎?')).toBeTruthy();
    expect(screen.queryByText('哪些人不適合 PRP?')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /顯示全部 7 題/ }));

    expect(screen.getByText('哪些人不適合 PRP?')).toBeTruthy();
    expect(screen.getByRole('button', { name: '收合' })).toBeTruthy();
  });
});
