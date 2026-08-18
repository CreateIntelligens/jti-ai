import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import MiniCalendar from '../../src/components/MiniCalendar';
import ConversationHistoryModal from '../../src/components/ConversationHistoryModal';
import * as apiServices from '../../src/services/api';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh' },
  }),
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('MiniCalendar with minDate and maxDate', () => {
  it('disables days before minDate and after maxDate', () => {
    const handleChange = vi.fn();
    render(
      <MiniCalendar
        label="選擇日期"
        value="2026-06-15"
        onChange={handleChange}
        minDate="2026-06-10"
        maxDate="2026-06-20"
      />
    );

    const day5Btn = screen.getByRole('button', { name: '5' }) as HTMLButtonElement;
    const day15Btn = screen.getByRole('button', { name: '15' }) as HTMLButtonElement;
    const day25Btn = screen.getByRole('button', { name: '25' }) as HTMLButtonElement;

    expect(day5Btn.disabled).toBe(true);
    expect(day15Btn.disabled).toBe(false);
    expect(day25Btn.disabled).toBe(true);

    // Clicking disabled day does not fire onChange
    fireEvent.click(day5Btn);
    expect(handleChange).not.toHaveBeenCalled();

    // Clicking enabled day fires onChange
    fireEvent.click(day15Btn);
    expect(handleChange).toHaveBeenCalledWith('');
  });

  it('prevents navigation beyond minDate and maxDate months', () => {
    const handleChange = vi.fn();
    const { container } = render(
      <MiniCalendar
        label=""
        value="2026-06-15"
        onChange={handleChange}
        minDate="2026-06-01"
        maxDate="2026-06-30"
      />
    );

    const navButtons = container.querySelectorAll('.mini-cal-nav');
    expect(navButtons.length).toBe(2);
    const prevBtn = navButtons[0] as HTMLButtonElement;
    const nextBtn = navButtons[1] as HTMLButtonElement;

    expect(prevBtn.disabled).toBe(true);
    expect(nextBtn.disabled).toBe(true);
  });
});

describe('ConversationHistoryModal HCIoT date limit restrictions', () => {
  beforeEach(() => {
    vi.spyOn(apiServices, 'fetchAsAdmin').mockImplementation(async (url: string) => {
      if (url.includes('/export')) {
        return {
          ok: true,
          json: async () => ({
            exported_at: '2026-08-18T20:00:00',
            mode: 'hciot',
            sessions: [
              {
                session_id: 'test-sid',
                first_message_time: '2026-08-18T10:00:00',
                total: 1,
                conversations: [],
              },
            ],
            total_conversations: 1,
            total_sessions: 1,
          }),
        } as Response;
      }
      return {
        ok: true,
        json: async () => ({
          mode: 'hciot',
          sessions: [
            {
              session_id: 'test-sid',
              first_message_time: '2026-08-18T10:00:00',
              total: 1,
              first_message: '你好',
            },
          ],
          total_sessions: 1,
          page: 1,
          page_size: 20,
        }),
      } as Response;
    });
  });

  it('alerts and prevents export when date is older than 3 months in HCIoT mode', async () => {
    const alertMock = vi.spyOn(window, 'alert').mockImplementation(() => {});

    const { container } = render(
      <ConversationHistoryModal
        isOpen={true}
        onClose={() => {}}
        mode="hciot"
      />
    );

    const exportBtn = await waitFor(() => {
      const btn = container.querySelector('.conversation-toolbar button:not(.batch-delete-btn):not(.select-all-btn)') as HTMLButtonElement;
      expect(btn).not.toBeNull();
      return btn;
    });

    const inputs = screen.getAllByRole('textbox');
    // inputs[0] is search, inputs[1] is dateFrom, inputs[2] is dateTo
    const dateFromInput = inputs[1];

    // Enter a date 5 months ago
    fireEvent.change(dateFromInput, { target: { value: '2026-01-01' } });
    fireEvent.submit(dateFromInput);

    fireEvent.click(exportBtn);

    expect(alertMock).toHaveBeenCalledWith(
      expect.stringContaining('下載區間限制為近三個月內')
    );
  });

  it('allows export when date is within 3 months and passes date_from and date_to params', async () => {
    const fetchSpy = vi.spyOn(apiServices, 'fetchAsAdmin');
    const alertMock = vi.spyOn(window, 'alert').mockImplementation(() => {});

    const { container } = render(
      <ConversationHistoryModal
        isOpen={true}
        onClose={() => {}}
        mode="hciot"
      />
    );

    const exportBtn = await waitFor(() => {
      const btn = container.querySelector('.conversation-toolbar button:not(.batch-delete-btn):not(.select-all-btn)') as HTMLButtonElement;
      expect(btn).not.toBeNull();
      return btn;
    });

    // Mock createObjectURL & revokeObjectURL
    window.URL.createObjectURL = vi.fn(() => 'blob:test');
    window.URL.revokeObjectURL = vi.fn();

    fireEvent.click(exportBtn);

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.stringMatching(/\/api\/hciot-admin\/conversations\/export\?date_from=/)
      );
    });
    expect(alertMock).not.toHaveBeenCalled();
  });
});
