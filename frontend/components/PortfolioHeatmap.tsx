'use client';

import { Treemap, ResponsiveContainer } from 'recharts';
import type { Position } from '@/lib/types';

interface Props {
  positions: Position[];
}

function colorFor(pnlPct: number): string {
  const clamped = Math.max(-10, Math.min(10, pnlPct));
  const strength = Math.min(1, Math.abs(clamped) / 10);
  if (clamped >= 0) {
    const g = Math.round(80 + strength * 140);
    return `rgb(34, ${g}, 94)`;
  }
  const r = Math.round(120 + strength * 130);
  return `rgb(${r}, 70, 70)`;
}

interface TreemapCellProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  payload?: { ticker: string; pnl_percent: number };
  name?: string;
  pnl_percent?: number;
}

function TreemapCell(props: TreemapCellProps) {
  const { x = 0, y = 0, width = 0, height = 0, name, pnl_percent = 0 } = props;
  const fill = colorFor(pnl_percent);
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill={fill} stroke="#0d1117" strokeWidth={2} />
      {width > 50 && height > 24 && (
        <>
          <text x={x + 6} y={y + 16} fill="#fff" fontSize={12} fontWeight={600}>
            {name}
          </text>
          <text x={x + 6} y={y + 32} fill="#fff" fontSize={10}>
            {pnl_percent >= 0 ? '+' : ''}{pnl_percent.toFixed(2)}%
          </text>
        </>
      )}
    </g>
  );
}

export function PortfolioHeatmap({ positions }: Props) {
  const data = positions.map((p) => ({
    ticker: p.ticker,
    name: p.ticker,
    size: Math.max(Math.abs(p.quantity * p.current_price), 1),
    pnl_percent: p.pnl_percent,
  }));

  if (data.length === 0) {
    return (
      <div className="dim" style={{ padding: 20, textAlign: 'center' }}>
        No positions yet — buy something from the trade bar or ask the assistant.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <Treemap
        data={data}
        dataKey="size"
        aspectRatio={4 / 3}
        stroke="#0d1117"
        content={<TreemapCell />}
      />
    </ResponsiveContainer>
  );
}
