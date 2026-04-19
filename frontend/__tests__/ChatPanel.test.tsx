import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatPanel } from '@/components/ChatPanel';

describe('ChatPanel', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn().mockImplementation(() =>
      new Promise((resolve) => {
        setTimeout(() => resolve({
          ok: true,
          json: async () => ({
            message: 'Done! Bought 2 AAPL at $190.',
            trades: [{ ticker: 'AAPL', side: 'buy', quantity: 2, price: 190.0 }],
            watchlist_changes: [],
            errors: [],
          }),
        }), 20);
      })
    ) as unknown as typeof fetch;
  });

  it('shows loading state then renders trade confirmations', async () => {
    const user = userEvent.setup();
    render(<ChatPanel onActionsApplied={() => {}} />);

    await user.type(screen.getByLabelText('Chat message'), 'buy 2 AAPL');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    expect(await screen.findByTestId('chat-loading')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId('chat-actions').textContent).toMatch(/BUY 2 AAPL/);
    });
    expect(screen.queryByTestId('chat-loading')).not.toBeInTheDocument();
  });
});
