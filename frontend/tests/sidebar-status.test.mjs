import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('sidebar project selector stays clickable when only the fallback option exists', async () => {
  const source = await readFile(new URL('../src/components/Sidebar.tsx', import.meta.url), 'utf8');

  assert.match(source, /PROJECT_SELECT_FALLBACK_OPTIONS/);
  assert.match(source, /hasProjectFilterOptions/);
  assert.match(source, /projectSelectOptions/);
  assert.match(source, /projectSelectValue/);
  assert.doesNotMatch(source, /disabled=\{!hasProjectFilterOptions\}/);
});

test('status message is rendered as a fixed toast instead of inside header layout', async () => {
  const appSource = await readFile(new URL('../src/App.tsx', import.meta.url), 'utf8');
  const headerSource = await readFile(new URL('../src/components/Header.tsx', import.meta.url), 'utf8');
  const layoutCss = await readFile(new URL('../src/styles/app/layout.css', import.meta.url), 'utf8');

  assert.doesNotMatch(headerSource, /className="status"/);
  assert.match(appSource, /className="status-toast"/);
  assert.match(layoutCss, /\.status-toast\s*\{[^}]*position:\s*fixed/s);
  assert.match(layoutCss, /\.status-toast\s*\{[^}]*pointer-events:\s*none/s);
  assert.match(layoutCss, /@keyframes statusToast/);
});
