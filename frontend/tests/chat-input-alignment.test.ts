import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const shellCss = readFileSync(join(process.cwd(), 'src/styles/app/shell.css'), 'utf8');

function readRuleBody(selector: string) {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = shellCss.match(new RegExp(`(?:^|\\n)${escapedSelector}\\s*\\{([^}]*)\\}`));
  return match?.[1] ?? '';
}

describe('home chat input alignment', () => {
  it('centers the send button against the textarea row', () => {
    const inputWrap = readRuleBody('.input-wrap');
    const sendButton = readRuleBody('.send-btn');
    const scopedSendButton = readRuleBody('.app-shell .input-area button.send-btn');
    const sendIcon = readRuleBody('.send-btn svg');

    // 多行輸入時送出鈕對齊輸入列底部（flex-end），而非垂直置中。
    expect(inputWrap).toContain('align-items: flex-end');
    expect(sendButton).toContain('padding: 0');
    expect(sendButton).toContain('box-sizing: border-box');
    expect(sendButton).toContain('line-height: 0');
    expect(sendButton).toContain('width: 2rem');
    expect(sendButton).toContain('height: 2rem');
    expect(scopedSendButton).toContain('padding: 0');
    expect(scopedSendButton).toContain('width: 2rem');
    expect(scopedSendButton).toContain('height: 2rem');
    expect(scopedSendButton).toContain('flex: 0 0 2rem');
    expect(sendIcon).toContain('width: .9375rem');
    expect(sendIcon).toContain('height: .9375rem');
    expect(sendIcon).toContain('flex: 0 0 .9375rem');
  });

  it('uses a tonal disabled state instead of fading the whole button', () => {
    const disabledButton = readRuleBody('.send-btn:disabled');

    expect(disabledButton).toContain('opacity: 1');
    expect(disabledButton).toContain('background: var(--primary-lt)');
    expect(disabledButton).toContain('color: var(--primary)');
    expect(disabledButton).toContain('border-color: var(--border-md)');
    expect(disabledButton).toContain('box-shadow: none');
  });

  it('gives the enabled send action clear depth and interaction feedback', () => {
    const sendButton = readRuleBody('.send-btn');
    const hoverButton = readRuleBody('.send-btn:not(:disabled):hover');
    const activeButton = readRuleBody('.send-btn:not(:disabled):active');

    // Redesign 後改用 design token 的純色底 + 陰影（取代手調 gradient）。
    expect(sendButton).toContain('background: var(--primary)');
    expect(sendButton).toContain('box-shadow:');
    expect(hoverButton).toContain('transform: translateY(-.0625rem)');
    expect(hoverButton).toContain('background: var(--primary-dark)');
    expect(activeButton).toContain('transform: translateY(0)');
  });
});
