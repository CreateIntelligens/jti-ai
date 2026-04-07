import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

test('does not keep HCIoT TTS selection state inside the shared persona tab', async () => {
  const source = await readFile(new URL('../src/components/jti/JtiPersonaTab.tsx', import.meta.url), 'utf8');

  assert.doesNotMatch(source, /ttsCharacters\?: string\[\];/);
  assert.doesNotMatch(source, /updateTtsCharacter/);
  assert.doesNotMatch(source, /ttsCharacterOptions/);
});
