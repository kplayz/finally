import { describe, it, expect, vi } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Watchlist } from '@/components/Watchlist';
import type { PriceEvent, WatchlistEntry } from '@/lib/types';

const entry: WatchlistEntry = {
  ticker: 'AAPL',
  price: 190.0,
  previous_price: 190.0,
  added_at: '2026-04-18T00:00:00Z',
};

function priceEvent(price: number): PriceEvent {
  return {
    ticker: 'AAPL',
    price,
    previous_price: 190.0,
    timestamp: '2026-04-18T00:00:01Z',
    direction: price >= 190.0 ? 'up' : 'down',
  };
}

describe('Watchlist', () => {
  it('applies price-flash-up when price increases', async () => {
    const { rerender } = render(
      <Watchlist
        entries={[entry]}
        prices={{ AAPL: priceEvent(190.0) }}
        history={{}}
        selected={null}
        onSelect={() => {}}
        onAdd={async () => {}}
        onRemove={async () => {}}
      />,
    );
    rerender(
      <Watchlist
        entries={[entry]}
        prices={{ AAPL: priceEvent(191.5) }}
        history={{}}
        selected={null}
        onSelect={() => {}}
        onAdd={async () => {}}
        onRemove={async () => {}}
      />,
    );
    const priceCell = screen.getByTestId('price-AAPL');
    // Flash applied synchronously on re-render via effect
    await act(async () => { await Promise.resolve(); });
    expect(priceCell.className).toContain('price-flash-up');
  });

  it('calls onAdd when submitting a ticker', async () => {
    const user = userEvent.setup();
    const onAdd = vi.fn().mockResolvedValue(undefined);
    render(
      <Watchlist
        entries={[entry]}
        prices={{}}
        history={{}}
        selected={null}
        onSelect={() => {}}
        onAdd={onAdd}
        onRemove={async () => {}}
      />,
    );
    await user.type(screen.getByLabelText('Add ticker'), 'amd');
    await user.click(screen.getByRole('button', { name: 'Add' }));
    expect(onAdd).toHaveBeenCalledWith('AMD');
  });
});
