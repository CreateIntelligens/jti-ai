import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const layoutCss = readFileSync(join(process.cwd(), 'src/styles/qaWorkspace/layout.css'), 'utf8');

function readRuleBody(selector: string) {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = layoutCss.match(new RegExp(`${escapedSelector}\\s*\\{([^}]*)\\}`));
  return match?.[1] ?? '';
}

describe('Hciot header layering', () => {
  it('keeps header menus above the main workspace', () => {
    const headerBody = readRuleBody('.qa-header');
    const zIndex = headerBody.match(/z-index:\s*(\d+)/)?.[1];

    expect(Number(zIndex)).toBeGreaterThan(1);
  });
});
