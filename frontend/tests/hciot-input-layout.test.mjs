import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

test('uses a flexible sidebar width and a wrapping input footer for HCIoT chat', async () => {
  const [layoutCss, componentsCss] = await Promise.all([
    readFile(new URL('../src/styles/hciot/layout.css', import.meta.url), 'utf8'),
    readFile(new URL('../src/styles/hciot/components.css', import.meta.url), 'utf8'),
  ]);

  assert.match(
    layoutCss,
    /\.hciot-main\s*\{[\s\S]*grid-template-columns:\s*clamp\(15\.5rem,\s*22vw,\s*19rem\)\s+minmax\(0,\s*1fr\);/,
  );
  assert.match(
    layoutCss,
    /\.hciot-main\s*\{[\s\S]*max-width:\s*90rem;/,
  );
  assert.match(
    componentsCss,
    /\.hciot-input-footer\s*\{[\s\S]*flex-wrap:\s*wrap;/,
  );
  assert.match(
    componentsCss,
    /\.hciot-inline-status\s*\{[\s\S]*flex-wrap:\s*wrap;/,
  );
});
