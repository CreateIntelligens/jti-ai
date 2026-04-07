import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

test('keeps HCIoT TTS selection on the page instead of inside the settings modal', async () => {
  const [pageSource, modalSource, apiSource] = await Promise.all([
    readFile(new URL('../../src/pages/Hciot.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../../src/components/HciotSettingsModal.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../../src/services/api/hciot.ts', import.meta.url), 'utf8'),
  ]);

  assert.match(pageSource, /const \[ttsCharacters, setTtsCharacters\] = useState<string\[\]>\(\[\]\);/);
  assert.match(pageSource, /const \[selectedTtsCharacter, setSelectedTtsCharacter\] = useState<string>\(/);
  assert.match(pageSource, /api\.getHciotTtsCharacters\(\)/);
  assert.match(pageSource, /hciotSendMessage\(\s*message,\s*activeSessionId,\s*turnNumber,\s*selectedTtsCharacter,\s*\)/);
  assert.match(pageSource, /character:\s*selectedTtsCharacter \|\| undefined/);

  assert.doesNotMatch(modalSource, /getHciotTtsCharacters/);
  assert.doesNotMatch(modalSource, /ttsCharacters=/);

  assert.match(
    apiSource,
    /hciotSendMessage\(\s*text: string,\s*sessionId: string,\s*turnNumber\?: number,\s*ttsCharacter\?: string,\s*\)/,
  );
  assert.match(apiSource, /payload\.tts_character = ttsCharacter;/);
});
