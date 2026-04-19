import { expect, it } from 'vitest';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import HciotInputArea from '../../src/components/hciot/HciotInputArea';

it('renders the prototype-style input status hint', () => {
  const html = renderToStaticMarkup(
    <HciotInputArea
      userInput=""
      loading={false}
      sessionId="abc123456"
      statusText="已連線"
      sessionInfo="#abc12345"
      placeholder="請輸入問題"
      setUserInput={() => {}}
      handleSubmit={(event) => event.preventDefault()}
      handleKeyDown={() => {}}
      inputRef={{ current: null }}
      // @ts-expect-error TDD: hintText is added when the prototype shell is ported.
      hintText="Enter 傳送, Shift+Enter 換行"
    />,
  );

  expect(html).toMatch(/Enter 傳送, Shift\+Enter 換行/);
});
