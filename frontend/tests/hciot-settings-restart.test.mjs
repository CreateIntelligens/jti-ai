import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

test('uses a silent restart callback for HCIoT settings changes', async () => {
  const source = await readFile(new URL('../src/pages/Hciot.tsx', import.meta.url), 'utf8');

  assert.match(
    source,
    /const silentRestartConversation = useCallback\(async \(\) => \{/,
  );
  assert.match(
    source,
    /<HciotSettingsModal[\s\S]*onPromptChange={silentRestartConversation}/,
  );
  assert.doesNotMatch(
    source,
    /<HciotSettingsModal[\s\S]*onPromptChange={restartConversation}/,
  );
});
