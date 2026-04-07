import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

test('keeps HCIoT TTS selection on the page instead of inside the settings modal', async () => {
  const [pageSource, modalSource, apiSource] = await Promise.all([
    readFile(new URL('../src/pages/Hciot.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/HciotSettingsModal.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/services/api/hciot.ts', import.meta.url), 'utf8'),
  ]);

  assert.match(pageSource, /const TTS_CHARACTER_STORAGE_KEY = 'hciot:tts-character';/);
  assert.match(pageSource, /function readStoredTtsCharacter\(\): string/);
  assert.match(pageSource, /function writeStoredTtsCharacter\(value: string\): void/);
  assert.match(pageSource, /function resolveTtsCharacter\(characters: string\[\], preferredValue\?: string\): string/);
  assert.match(pageSource, /const \[ttsCharacters, setTtsCharacters\] = useState<string\[\]>\(\[\]\);/);
  assert.match(pageSource, /const \[selectedTtsCharacter, setSelectedTtsCharacter\] = useState<string>\(/);
  assert.match(pageSource, /\(\) => readStoredTtsCharacter\(\)/);
  assert.match(pageSource, /const nextValue = resolveTtsCharacter\(availableCharacters, currentValue\);/);
  assert.match(pageSource, /writeStoredTtsCharacter\(selectedTtsCharacter\);/);
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
