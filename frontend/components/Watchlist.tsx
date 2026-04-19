'use client';

import { useEffect, useRef, useState } from 'react';
import { Sparkline } from './Sparkline';
import type { PriceEvent, PricePoint, WatchlistEntry } from '@/lib/types';

interface Props {
  entries: WatchlistEntry[];
  prices: Record<string, PriceEvent>;
  history: Record<string, PricePoint[]>;
  selected: string | null;
  onSelect: (ticker: string) => void;
  onAdd: (ticker: string) => Promise<void> | void;
  onRemove: (ticker: string) => Promise<void> | void;
}

const fmt = (n: number | null | undefined) =>
  n == null ? '—' : n.toFixed(2);

const changePct = (entry: WatchlistEntry, live?: PriceEvent): number | null => {
  const prev = live?.previous_price ?? entry.previous_price;
  const cur = live?.price ?? entry.price;
  if (prev == null || cur == null || prev === 0) return null;
  return ((cur - prev) / prev) * 100;
};

function Row({
  entry,
  live,
  history,
  selected,
  onSelect,
  onRemove,
}: {
  entry: WatchlistEntry;
  live: PriceEvent | undefined;
  history: PricePoint[];
  selected: boolean;
  onSelect: () => void;
  onRemove: () => void;
}) {
  const price = live?.price ?? entry.price;
  const direction = live?.direction;

  const [flashClass, setFlashClass] = useState('');
  const prevPriceRef = useRef<number | null>(price ?? null);
  useEffect(() => {
    if (price == null) return;
    const prev = prevPriceRef.current;
    if (prev != null && price !== prev) {
      const cls = price > prev ? 'price-flash-up' : 'price-flash-down';
      setFlashClass(cls);
      const t = setTimeout(() => setFlashClass(''), 500);
      return () => clearTimeout(t);
    }
    prevPriceRef.current = price;
  }, [price]);
  useEffect(() => {
    prevPriceRef.current = price ?? null;
  }, [price]);

  const pct = changePct(entry, live);

  return (
    <tr
      className={selected ? 'selected' : ''}
      onClick={onSelect}
      data-testid={`watchlist-row-${entry.ticker}`}
    >
      <td style={{ fontWeight: 600 }}>{entry.ticker}</td>
      <td
        className={flashClass}
        data-testid={`price-${entry.ticker}`}
        style={{ fontVariantNumeric: 'tabular-nums' }}
      >
        {fmt(price)}
      </td>
      <td
        className={pct == null ? 'dim' : pct >= 0 ? 'up' : 'down'}
        style={{ fontVariantNumeric: 'tabular-nums' }}
      >
        {pct == null ? '—' : `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`}
      </td>
      <td><Sparkline points={history} /></td>
      <td>
        <button
          onClick={(e) => { e.stopPropagation(); onRemove(); }}
          aria-label={`Remove ${entry.ticker}`}
          title="Remove"
          style={{ padding: '2px 8px' }}
        >×</button>
      </td>
    </tr>
  );
}

export function Watchlist(props: Props) {
  const { entries, prices, history, selected, onSelect, onAdd, onRemove } = props;
  const [input, setInput] = useState('');
  const [error, setError] = useState<string | null>(null);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    const t = input.trim().toUpperCase();
    if (!t) return;
    setError(null);
    try {
      await onAdd(t);
      setInput('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add ticker');
    }
  };

  return (
    <div className="panel" style={{ gridArea: 'watchlist', overflow: 'auto' }}>
      <div className="panel-title">Watchlist</div>
      <table>
        <thead>
          <tr><th>Symbol</th><th>Price</th><th>Chg</th><th>Chart</th><th></th></tr>
        </thead>
        <tbody>
          {entries.map((e) => (
            <Row
              key={e.ticker}
              entry={e}
              live={prices[e.ticker]}
              history={history[e.ticker] ?? []}
              selected={selected === e.ticker}
              onSelect={() => onSelect(e.ticker)}
              onRemove={() => onRemove(e.ticker)}
            />
          ))}
        </tbody>
      </table>
      <form onSubmit={handleAdd} style={{ padding: 10, display: 'flex', gap: 6 }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Add ticker (e.g. AMD)"
          aria-label="Add ticker"
          style={{ flex: 1 }}
        />
        <button type="submit" className="btn-primary">Add</button>
      </form>
      {error && (
        <div className="down" style={{ padding: '0 10px 10px' }} role="alert">
          {error}
        </div>
      )}
    </div>
  );
}
