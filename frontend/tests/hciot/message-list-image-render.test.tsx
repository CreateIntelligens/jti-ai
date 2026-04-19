import { expect, it } from 'vitest';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import HciotMessageList, { type HciotMessage } from '../../src/components/hciot/HciotMessageList';

function renderMessages(messages: HciotMessage[]) {
  return renderToStaticMarkup(
    <HciotMessageList
      messages={messages}
      loading={false}
      isTyping={false}
      editingTurn={null}
      editText=""
      editTextareaRef={{ current: null }}
      messagesEndRef={{ current: null }}
      handleRegenerate={() => {}}
      handleEditAndResend={() => {}}
      setEditingTurn={() => {}}
      setEditText={() => {}}
      handleEditKeyDown={() => {}}
      heroEyebrow="eyebrow"
      heroTitle="title"
      heroDescription="description"
      heroNote="note"
    />,
  );
}

it('renders an inline HCIoT image preview when imageId is present', () => {
  const html = renderMessages([
    {
      text: '這是您的衛教說明。',
      type: 'assistant',
      timestamp: 1,
      imageId: 'hciot-demo-image',
    },
  ]);

  expect(html).toMatch(/src="\/api\/hciot\/images\/hciot-demo-image"/);
});
