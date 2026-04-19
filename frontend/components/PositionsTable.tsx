'use client';

import type { Position, PriceEvent } from '@/lib/types';

interface Props {
  positions: Position[];
  prices: Record<string, PriceEvent>;
  onSelect: (ticker: string) => void;
}

const fmt = (n: number, d = 2) =>
  n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });

export function PositionsTable({ positions, prices, onSelect }: Props) {
  if (positions.length === 0) {
    return <div className="dim" style={{ padding: 20, textAlign: 'center' }}>No open positions.</div>;
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Ticker</th>
          <th>Qty</th>
          <th>Avg Cost</th>
          <th>Price</th>
          <th>P&amp;L</th>
          <th>%</th>
        </tr>
      </thead>
      <tbody>
        {positions.map((p) => {
          const live = prices[p.ticker]?.price ?? p.current_price;
          const pnl = (live - p.avg_cost) * p.quantity;
          const pct = p.avg_cost === 0 ? 0 : ((live - p.avg_cost) / p.avg_cost) * 100;
          const cls = pnl >= 0 ? 'up' : 'down';
          return (
            <tr key={p.ticker} onClick={() => onSelect(p.ticker)}>
              <td style={{ fontWeight: 600 }}>{p.ticker}</td>
              <td>{fmt(p.quantity, 4).replace(/\.?0+$/, '')}</td>
              <td>${fmt(p.avg_cost)}</td>
              <td>${fmt(live)}</td>
              <td className={cls}>{pnl >= 0 ? '+' : ''}${fmt(pnl)}</td>
              <td className={cls}>{pct >= 0 ? '+' : ''}{fmt(pct)}%</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
