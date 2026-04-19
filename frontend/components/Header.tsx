'use client';

import type { ConnectionState } from '@/lib/types';

interface Props {
  totalValue: number;
  cashBalance: number;
  connectionState: ConnectionState;
  onReset: () => void;
}

function dotClass(state: ConnectionState): string {
  if (state === 'open') return 'dot dot-green';
  if (state === 'closed') return 'dot dot-red';
  return 'dot dot-yellow';
}

const fmt = (n: number) =>
  n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function Header({ totalValue, cashBalance, connectionState, onReset }: Props) {
  return (
    <div
      style={{
        gridArea: 'header',
        display: 'flex',
        alignItems: 'center',
        padding: '8px 16px',
        border: '1px solid var(--border)',
        borderRadius: 6,
        background: 'var(--panel)',
        gap: 24,
      }}
    >
      <div style={{ fontWeight: 600, fontSize: 16, color: 'var(--accent-yellow)' }}>
        FinAlly
      </div>
      <div style={{ display: 'flex', gap: 24, marginLeft: 'auto', alignItems: 'center' }}>
        <div>
          <span className="dim" style={{ marginRight: 8 }}>TOTAL</span>
          <span data-testid="total-value" style={{ fontVariantNumeric: 'tabular-nums' }}>
            ${fmt(totalValue)}
          </span>
        </div>
        <div>
          <span className="dim" style={{ marginRight: 8 }}>CASH</span>
          <span data-testid="cash-balance" style={{ fontVariantNumeric: 'tabular-nums' }}>
            ${fmt(cashBalance)}
          </span>
        </div>
        <div
          data-testid="connection-status"
          data-state={connectionState}
          title={`SSE: ${connectionState}`}
          style={{ display: 'flex', alignItems: 'center', gap: 6 }}
        >
          <span className={dotClass(connectionState)} />
          <span className="dim">{connectionState}</span>
        </div>
        <button onClick={onReset} title="Reset account to initial state">Reset</button>
      </div>
    </div>
  );
}
