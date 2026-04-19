'use client';

import { useEffect, useRef } from 'react';
import { createChart, ColorType, type IChartApi, type ISeriesApi, type Time } from 'lightweight-charts';
import type { PricePoint } from '@/lib/types';

interface Props {
  ticker: string | null;
  history: PricePoint[];
}

export function MainChart({ ticker, history }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 300,
      layout: {
        background: { type: ColorType.Solid, color: '#161b22' },
        textColor: '#8b949e',
      },
      grid: {
        vertLines: { color: '#2a3140' },
        horzLines: { color: '#2a3140' },
      },
      timeScale: { timeVisible: true, secondsVisible: true, borderColor: '#2a3140' },
      rightPriceScale: { borderColor: '#2a3140' },
    });
    const series = chart.addLineSeries({
      color: '#209dd7',
      lineWidth: 2,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    });
    chartRef.current = chart;
    seriesRef.current = series;

    const ro = new ResizeObserver(() => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!seriesRef.current) return;
    if (history.length === 0) {
      seriesRef.current.setData([]);
      return;
    }
    // Dedup by second-granularity time (Lightweight Charts requires unique ascending times).
    const seen = new Set<number>();
    const data: { time: Time; value: number }[] = [];
    for (const p of history) {
      const t = Math.floor(p.t / 1000) as number;
      if (!seen.has(t)) {
        seen.add(t);
        data.push({ time: t as Time, value: p.price });
      } else {
        // overwrite with latest price in the same second
        data[data.length - 1] = { time: t as Time, value: p.price };
      }
    }
    seriesRef.current.setData(data);
  }, [history]);

  return (
    <div className="panel" style={{ gridArea: 'main', display: 'flex', flexDirection: 'column' }}>
      <div className="panel-title">
        {ticker ? `${ticker} — live` : 'Select a ticker'}
      </div>
      <div ref={containerRef} style={{ flex: 1, minHeight: 300 }} />
    </div>
  );
}
