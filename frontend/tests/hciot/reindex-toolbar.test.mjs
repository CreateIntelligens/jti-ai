import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('HCIoT reindex action is separated and warns about service pause', async () => {
  const sidebarSource = await readFile(
    new URL('../../src/components/hciot/knowledgeWorkspace/explorer/ExplorerSidebar.tsx', import.meta.url),
    'utf8',
  );
  const workspaceCss = await readFile(
    new URL('../../src/styles/hciot/workspace.css', import.meta.url),
    'utf8',
  );

  assert.match(sidebarSource, /className="hciot-explorer-actions"/);
  assert.match(sidebarSource, /className="hciot-explorer-icon-button reindex"/);
  assert.match(sidebarSource, /aria-label="重新索引 RAG"/);
  assert.match(sidebarSource, /暫停約 1 分鐘/);
  assert.match(workspaceCss, /\.hciot-explorer-actions\s*\{[^}]*gap:\s*0\.55rem/s);
  assert.match(workspaceCss, /\.hciot-explorer-icon-button\.reindex/s);
});
