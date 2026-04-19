'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { Side, TradeResponse } from '@/lib/types';

interface Props {
  defaultTicker?: string | null;
  onTrade: (res: TradeResponse) => void;
}

export function TradeBar({ defaultTicker, onTrade }: Props) {
  const [ticker, setTicker] = useState(defaultTicker ?? '');
  const [quantity, setQuantity] = useState('1');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (defaultTicker) setTicker(defaultTicker);
  }, [defaultTicker]);

  const submit = async (side: Side) => {
    setError(null);
    const qty = parseFloat(quantity);
    const sym = ticker.trim().toUpperCase();
    if (!sym) { setError('Enter a ticker'); return; }
    if (!Number.isFinite(qty) || qty <= 0) { setError('Quantity must be a positive number'); return; }
    setBusy(true);
    try {
      const res = await api.trade({ ticker: sym, quantity: qty, side });
      onTrade(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Trade failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel" style={{ gridArea: 'trade', padding: 10 }}>
      <div className="panel-title" style={{ marginBottom: 8, padding: 0, border: 'none' }}>Trade</div>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        <input
          aria-label="Ticker"
          placeholder="TICKER"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          style={{ width: 90 }}
        />
        <input
          aria-label="Quantity"
          type="number"
          step="0.01"
          min="0"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          style={{ width: 90 }}
        />
        <button
          className="btn-buy"
          disabled={busy}
          onClick={() => submit('buy')}
          data-testid="buy-button"
        >Buy</button>
        <button
          className="btn-sell"
          disabled={busy}
          onClick={() => submit('sell')}
          data-testid="sell-button"
        >Sell</button>
      </div>
      {error && (
        <div className="down" style={{ marginTop: 6 }} role="alert">{error}</div>
      )}
    </div>
  );
}
