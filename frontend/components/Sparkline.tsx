'use client';

import type { PricePoint } from '@/lib/types';

interface Props {
  points: PricePoint[];
  width?: number;
  height?: number;
}

export function Sparkline({ points, width = 80, height = 24 }: Props) {
  if (!points || points.length < 2) {
    return <svg width={width} height={height} aria-hidden="true" />;
  }
  const ys = points.map((p) => p.price);
  const min = Math.min(...ys);
  const max = Math.max(...ys);
  const range = max - min || 1;
  const step = width / (points.length - 1);
  const path = points
    .map((p, i) => {
      const x = i * step;
      const y = height - ((p.price - min) / range) * height;
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  const up = points[points.length - 1].price >= points[0].price;
  return (
    <svg width={width} height={height} aria-hidden="true">
      <path
        d={path}
        fill="none"
        stroke={up ? 'var(--up)' : 'var(--down)'}
        strokeWidth="1.5"
      />
    </svg>
  );
}
