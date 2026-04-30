import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('home header is a compact command bar with responsive labels', async () => {
  const source = await readFile(new URL('../src/components/Header.tsx', import.meta.url), 'utf8');
  const css = await readFile(new URL('../src/styles/app/layout.css', import.meta.url), 'utf8');

  assert.match(source, /PanelLeftClose|PanelLeftOpen/);
  assert.match(source, /header-link-label/);
  assert.match(source, /重建索引/);
  assert.doesNotMatch(source, /[◧◨]/);
  assert.match(css, /\.app-content\s*\{[^}]*position:\s*relative/s);
  assert.match(css, /\.app-container header\s*\{[^}]*min-height:\s*4rem/s);
  assert.match(css, /\.header-actions\s*\{[^}]*flex-wrap:\s*wrap/s);
  assert.match(css, /@media \(max-width:\s*1180px\)[\s\S]*\.header-link-label\s*\{[^}]*display:\s*none/s);
  assert.match(css, /@media \(max-width:\s*768px\)[\s\S]*\.app-container header\s*\{[^}]*flex-wrap:\s*wrap/s);
  assert.match(css, /@media \(max-width:\s*768px\)[\s\S]*\.header-actions\s*\{[^}]*overflow-x:\s*auto/s);
  assert.match(css, /@media \(max-width:\s*768px\)[\s\S]*\.app-container aside\s*\{[^}]*top:\s*0/s);
  assert.doesNotMatch(css, /animation:\s*titleGlow/);
});

test('chat canvas uses restrained empty state and icon send action', async () => {
  const source = await readFile(new URL('../src/components/ChatArea.tsx', import.meta.url), 'utf8');
  const layoutCss = await readFile(new URL('../src/styles/app/layout.css', import.meta.url), 'utf8');
  const componentsCss = await readFile(new URL('../src/styles/app/components.css', import.meta.url), 'utf8');

  assert.match(source, /SendHorizontal/);
  assert.doesNotMatch(source, /✧/);
  assert.doesNotMatch(source, /Shift\+Enter|Enter 傳送/);
  assert.match(layoutCss, /\.app-container main\s*\{[^}]*border-radius:\s*1rem/s);
  assert.match(layoutCss, /\.input-area\s*\{[^}]*padding:\s*1rem/s);
  assert.match(componentsCss, /\.empty-state\s*\{[^}]*margin:\s*auto/s);
  assert.doesNotMatch(componentsCss, /animation:\s*pulse/);
});
