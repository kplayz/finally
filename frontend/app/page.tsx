'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Header } from '@/components/Header';
import { Watchlist } from '@/components/Watchlist';
import { MainChart } from '@/components/MainChart';
import { PortfolioHeatmap } from '@/components/PortfolioHeatmap';
import { PnLChart } from '@/components/PnLChart';
import { PositionsTable } from '@/components/PositionsTable';
import { TradeBar } from '@/components/TradeBar';
import { ChatPanel } from '@/components/ChatPanel';
import { useSSE } from '@/lib/useSSE';
import { api } from '@/lib/api';
import type { Portfolio, Snapshot, WatchlistEntry } from '@/lib/types';

export default function Home() {
  const { prices, priceHistory, connectionState } = useSSE();
  const [watchlist, setWatchlist] = useState<WatchlistEntry[]>([]);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [selected, setSelected] = useState<string | null>(null);

  const refreshAll = useCallback(async () => {
    const [wl, pf, hist] = await Promise.all([
      api.getWatchlist().catch(() => ({ watchlist: [] })),
      api.getPortfolio().catch(() => null),
      api.getPortfolioHistory().catch(() => ({ snapshots: [] })),
    ]);
    setWatchlist(wl.watchlist);
    setPortfolio(pf);
    setSnapshots(hist.snapshots);
    if (!selected && wl.watchlist.length > 0) {
      setSelected(wl.watchlist[0].ticker);
    }
  }, [selected]);

  useEffect(() => {
    refreshAll();
    const t = setInterval(refreshAll, 10_000);
    return () => clearInterval(t);
  }, [refreshAll]);

  const addTicker = async (ticker: string) => {
    const res = await api.addWatchlistTicker(ticker);
    setWatchlist(res.watchlist);
    if (!selected) setSelected(ticker);
  };
  const removeTicker = async (ticker: string) => {
    const res = await api.removeWatchlistTicker(ticker);
    setWatchlist(res.watchlist);
    if (selected === ticker) setSelected(res.watchlist[0]?.ticker ?? null);
  };

  const handleReset = async () => {
    if (!confirm('Reset account to $10,000 and default watchlist?')) return;
    await api.reset();
    await refreshAll();
  };

  const liveTotal = useMemo(() => {
    if (!portfolio) return 0;
    const positionsValue = portfolio.positions.reduce((acc, p) => {
      const live = prices[p.ticker]?.price ?? p.current_price;
      return acc + p.quantity * live;
    }, 0);
    return portfolio.cash_balance + positionsValue;
  }, [portfolio, prices]);

  const selectedHistory = selected ? priceHistory[selected] ?? [] : [];

  return (
    <div className="grid">
      <Header
        totalValue={liveTotal}
        cashBalance={portfolio?.cash_balance ?? 0}
        connectionState={connectionState}
        onReset={handleReset}
      />
      <Watchlist
        entries={watchlist}
        prices={prices}
        history={priceHistory}
        selected={selected}
        onSelect={setSelected}
        onAdd={addTicker}
        onRemove={removeTicker}
      />
      <MainChart ticker={selected} history={selectedHistory} />
      <ChatPanel onActionsApplied={refreshAll} />
      <TradeBar
        defaultTicker={selected}
        onTrade={() => refreshAll()}
      />
      <div
        className="panel"
        style={{ gridArea: 'positions', overflow: 'auto', display: 'flex', flexDirection: 'column' }}
      >
        <div className="panel-title">Portfolio</div>
        <div style={{ padding: 10 }}>
          <div style={{ fontSize: 10, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.08em', margin: '6px 0' }}>
            Heatmap
          </div>
          <PortfolioHeatmap positions={portfolio?.positions ?? []} />
          <div style={{ fontSize: 10, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.08em', margin: '10px 0 6px' }}>
            Total Value
          </div>
          <PnLChart snapshots={snapshots} />
        </div>
        <PositionsTable
          positions={portfolio?.positions ?? []}
          prices={prices}
          onSelect={setSelected}
        />
      </div>
    </div>
  );
}
