import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('store management modal keeps key-owned store creation controls', async () => {
  const source = await readFile(new URL('../src/components/StoreManagementModal.tsx', import.meta.url), 'utf8');

  assert.match(source, /onCreateStore/);
  assert.match(source, /newStoreName|selectedKeyIndex|handleCreate/);
  assert.match(source, /建立新知識庫|建立中|✓ 建立/);
  assert.match(source, /import AppSelect, \{ type AppSelectOption \} from '\.\/AppSelect'/);
  assert.match(source, /className="store-create-row"/);
  assert.match(source, /className="store-key-select"/);
  assert.match(source, /contentClassName="store-key-select-content"/);
  assert.match(source, /className="store-key-static"/);
  assert.match(source, /buildStoreKeyOptions/);
  assert.match(source, /onCreateStore\(newStoreName\.trim\(\), Number\(selectedKeyValue\)\)/);
  assert.doesNotMatch(source, /store-key-select bento-minimal-select/);
  assert.doesNotMatch(source, /<select/);
  assert.doesNotMatch(source, /開啟管理/);
});

test('homepage wires store creation and deletion into the modal', async () => {
  const appSource = await readFile(new URL('../src/App.tsx', import.meta.url), 'utf8');
  const hookSource = await readFile(new URL('../src/hooks/useAppChat.ts', import.meta.url), 'utf8');

  assert.match(appSource, /onCreateStore=\{handleCreateStore\}/);
  assert.match(appSource, /onDeleteStore=\{handleDeleteStore\}/);
  assert.match(hookSource, /const handleCreateStore/);
  assert.match(hookSource, /const handleDeleteStore/);
});

test('store creation controls share one vertical rhythm', async () => {
  const css = await readFile(new URL('../src/styles/app/forms.css', import.meta.url), 'utf8');
  const lightCss = await readFile(new URL('../src/styles/app/light.css', import.meta.url), 'utf8');

  assert.match(css, /--store-create-control-height:\s*3\.125rem/);
  assert.match(css, /grid-template-columns:\s*minmax\(0,\s*1fr\)\s*minmax\(7\.5rem,\s*9rem\)\s*auto/);
  assert.doesNotMatch(css, /\.store-create-row\s*\{[^}]*flex-wrap/s);
  assert.match(css, /\.store-create-row\s*\{[^}]*align-items:\s*center/s);
  assert.match(css, /\.store-create-row input\s*\{[^}]*height:\s*var\(--store-create-control-height\)/s);
  assert.match(css, /\.app-select-trigger\.store-key-select\s*\{[^}]*height:\s*var\(--store-create-control-height\)/s);
  assert.match(css, /\.app-select-trigger\.store-key-select\s*\{[^}]*color:\s*#e0e6ff/s);
  assert.match(css, /\.store-key-select-content\s*\{[^}]*background:\s*rgba\(15,\s*20,\s*35,\s*0\.98\)/s);
  assert.match(css, /\.store-create-row button\s*\{[^}]*height:\s*var\(--store-create-control-height\)/s);
  assert.match(lightCss, /\[data-theme="light"\]\s+\.app-select-trigger\.store-key-select/s);
  assert.match(lightCss, /\[data-theme="light"\]\s+\.store-key-select-content/s);
});
