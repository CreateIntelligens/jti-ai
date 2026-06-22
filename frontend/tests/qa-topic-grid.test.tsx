import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';

import QaTopicGrid from '../src/components/_shared/QaTopicGrid';

it('sends the selected question text from the shared topic grid', () => {
  const onSelectQuestion = vi.fn();

  render(
    <QaTopicGrid
      topics={[
        {
          id: 'general/getting-started',
          label: '快速入門',
          questions: ['我要怎麼開始？'],
        },
      ]}
      onSelect={() => {}}
      onSelectQuestion={onSelectQuestion}
      selectedTopicId="general/getting-started"
    />,
  );

  fireEvent.click(screen.getByRole('button', { name: /我要怎麼開始/ }));

  expect(onSelectQuestion).toHaveBeenCalledWith('我要怎麼開始？');
});
