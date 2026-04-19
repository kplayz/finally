import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TradeBar } from '@/components/TradeBar';

describe('TradeBar', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ticker: 'AAPL', side: 'buy', quantity: 0.5, price: 191.25, total_cost: 95.625, cash_remaining: 9904.375,
      }),
    }) as unknown as typeof fetch;
  });

  it('submits fractional quantity to the trade endpoint', async () => {
    const user = userEvent.setup();
    const onTrade = vi.fn();
    render(<TradeBar defaultTicker="AAPL" onTrade={onTrade} />);

    const qty = screen.getByLabelText('Quantity');
    await user.clear(qty);
    await user.type(qty, '0.5');
    await user.click(screen.getByTestId('buy-button'));

    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/portfolio/trade',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ ticker: 'AAPL', quantity: 0.5, side: 'buy' }),
      }),
    );
    expect(onTrade).toHaveBeenCalled();
  });

  it('rejects non-positive quantity', async () => {
    const user = userEvent.setup();
    render(<TradeBar defaultTicker="AAPL" onTrade={() => {}} />);
    const qty = screen.getByLabelText('Quantity');
    await user.clear(qty);
    await user.type(qty, '0');
    await user.click(screen.getByTestId('buy-button'));
    expect(screen.getByRole('alert').textContent).toMatch(/positive/i);
  });
});
