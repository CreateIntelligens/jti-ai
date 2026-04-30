import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('home route mounts the generic store app instead of redirecting to a product page', async () => {
  const source = await readFile(new URL('../src/App.tsx', import.meta.url), 'utf8');

  assert.doesNotMatch(source, /function getHomePageTarget/);
  assert.doesNotMatch(source, /if \(page === 'home' && homePageTarget\)/);
  assert.doesNotMatch(source, /window\.history\.replaceState\(null, '', `\/\$\{homePageTarget\}`\);/);
  assert.match(source, /useAppChat\(\)/);
});
