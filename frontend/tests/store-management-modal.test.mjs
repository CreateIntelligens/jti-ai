import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('store management modal keeps key-owned store creation controls', async () => {
  const source = await readFile(new URL('../src/components/StoreManagementModal.tsx', import.meta.url), 'utf8');

  assert.match(source, /onCreateStore/);
  assert.match(source, /newStoreName|selectedKeyIndex|handleCreate/);
  assert.match(source, /建立新知識庫|建立中|✓ 建立/);
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
