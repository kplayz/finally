'use client';

import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import type { Snapshot } from '@/lib/types';

interface Props {
  snapshots: Snapshot[];
}

export function PnLChart({ snapshots }: Props) {
  const data = snapshots.map((s) => ({
    t: new Date(s.recorded_at).getTime(),
    value: s.total_value,
    label: new Date(s.recorded_at).toLocaleTimeString(),
  }));

  if (data.length < 2) {
    return (
      <div className="dim" style={{ padding: 20, textAlign: 'center' }}>
        P&amp;L chart populates once snapshots accumulate (every 30s + after trades).
      </div>
    );
  }

  const first = data[0].value;
  const last = data[data.length - 1].value;
  const stroke = last >= first ? '#22c55e' : '#ef4444';

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 6, right: 10, left: 0, bottom: 6 }}>
        <CartesianGrid stroke="#2a3140" strokeDasharray="3 3" />
        <XAxis dataKey="label" stroke="#6e7681" fontSize={10} tick={{ fill: '#8b949e' }} />
        <YAxis stroke="#6e7681" fontSize={10} tick={{ fill: '#8b949e' }} domain={['dataMin', 'dataMax']} />
        <Tooltip
          contentStyle={{ background: '#161b22', border: '1px solid #2a3140', color: '#e6edf3' }}
          formatter={(v: number) => `$${v.toFixed(2)}`}
        />
        <Line type="monotone" dataKey="value" stroke={stroke} strokeWidth={2} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
