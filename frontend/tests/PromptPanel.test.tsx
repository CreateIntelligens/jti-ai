import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import PromptPanel from '../src/components/PromptPanel';

const apiMocks = vi.hoisted(() => ({
  listPrompts: vi.fn(),
  fetchModels: vi.fn(),
  createPrompt: vi.fn(),
  updatePrompt: vi.fn(),
  deletePrompt: vi.fn(),
  setActivePrompt: vi.fn(),
}));

vi.mock('../src/services/api', () => ({
  ...apiMocks,
}));

describe('PromptPanel', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  function mockEnglishManagedPrompt() {
    apiMocks.listPrompts.mockResolvedValue({
      active_prompt_id: null,
      max_prompts: 3,
      prompts: [
        {
          id: 'system_default',
          name: '系統預設（HCIoT）',
          content: '你的名字是「小元」，你是元復醫院的衛教智慧助理。',
          content_en: 'Your name is Xiao-Yuan, the health education assistant for YuanFu Hospital.',
          response_rule_sections: {
            zh: { role_scope: '中文規則' },
            en: { role_scope: 'English rules' },
          },
          assembled: {
            zh: '完整中文系統 prompt',
            en: 'Full English system prompt marker\nEnglish rules',
          },
          readonly: true,
          is_default: true,
          is_active: true,
        },
      ],
    });
    apiMocks.fetchModels.mockResolvedValue({
      models: [],
      default_model: 'gemini-2.5-flash-lite',
    });
    apiMocks.createPrompt.mockResolvedValue({});
  }

  function renderEnglishPromptPanel(onClose = vi.fn()) {
    const result = render(
      <PromptPanel
        isOpen
        currentStore="__hciot__en"
        currentStoreName="HCIoT English"
        onClose={onClose}
        onRestartChat={vi.fn()}
      />,
    );

    return { ...result, onClose };
  }

  function getElement(container: HTMLElement, selector: string) {
    const element = container.querySelector(selector);
    expect(element).not.toBeNull();
    return element as HTMLElement;
  }

  it('shows the English persona preview for English managed General stores', async () => {
    mockEnglishManagedPrompt();

    renderEnglishPromptPanel();

    await waitFor(() => {
      expect(screen.getByText(/Your name is Xiao-Yuan/)).toBeTruthy();
    });
    expect(screen.queryByText(/你的名字是「小元」/)).toBeNull();
  });

  it('copies English managed defaults into the English draft fields', async () => {
    mockEnglishManagedPrompt();

    renderEnglishPromptPanel();

    fireEvent.click(await screen.findByRole('button', { name: '複製為自訂' }));

    expect(screen.getByDisplayValue(/Your name is Xiao-Yuan/)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: '儲存' }));

    await waitFor(() => {
      expect(apiMocks.createPrompt).toHaveBeenCalledWith(
        '__hciot__en',
        '自訂 1',
        '你的名字是「小元」，你是元復醫院的衛教智慧助理。',
        'Your name is Xiao-Yuan, the health education assistant for YuanFu Hospital.',
        {
          zh: { role_scope: '中文規則' },
          en: { role_scope: 'English rules' },
        },
        null,
      );
    });
  });

  it('previews readonly defaults without entering edit mode', async () => {
    mockEnglishManagedPrompt();

    renderEnglishPromptPanel();

    fireEvent.click(await screen.findByRole('button', { name: '預覽' }));

    expect(screen.getByDisplayValue(/Full English system prompt marker/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: '儲存' })).toBeNull();
  });

  it('closes prompt preview when switching stores', async () => {
    mockEnglishManagedPrompt();

    const { rerender } = renderEnglishPromptPanel();

    fireEvent.click(await screen.findByRole('button', { name: '預覽' }));
    expect(screen.getByDisplayValue(/Full English system prompt marker/)).toBeTruthy();

    rerender(
      <PromptPanel
        isOpen
        currentStore="__jti__en"
        currentStoreName="JTI English"
        onClose={vi.fn()}
        onRestartChat={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(apiMocks.listPrompts).toHaveBeenCalledTimes(2);
    });
    expect(screen.queryByDisplayValue(/Full English system prompt marker/)).toBeNull();
  });

  it('does not close when a press starts inside the panel and ends on the overlay', async () => {
    mockEnglishManagedPrompt();
    const { container, onClose } = renderEnglishPromptPanel();
    await screen.findByText(/Your name is Xiao-Yuan/);
    const overlay = getElement(container, '.rp-overlay');
    const panel = getElement(container, '.rp-panel');

    fireEvent.mouseDown(panel);
    fireEvent.mouseUp(overlay);
    fireEvent.click(overlay);

    expect(onClose).not.toHaveBeenCalled();
  });

  it('closes when a press starts and ends on the overlay', async () => {
    mockEnglishManagedPrompt();
    const { container, onClose } = renderEnglishPromptPanel();
    await screen.findByText(/Your name is Xiao-Yuan/);
    const overlay = getElement(container, '.rp-overlay');

    fireEvent.mouseDown(overlay);
    fireEvent.mouseUp(overlay);

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
