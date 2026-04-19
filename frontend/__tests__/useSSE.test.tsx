import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useSSE } from '@/lib/useSSE';

class MockEventSource {
  static CONNECTING = 0 as const;
  static OPEN = 1 as const;
  static CLOSED = 2 as const;
  onopen: ((ev: Event) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  readyState: number = MockEventSource.CONNECTING;
  url: string;
  static instances: MockEventSource[] = [];

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
    queueMicrotask(() => {
      this.readyState = MockEventSource.OPEN;
      this.onopen?.(new Event('open'));
    });
  }
  close() { this.readyState = MockEventSource.CLOSED; }
  emit(data: unknown) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(data) }));
  }
}

describe('useSSE', () => {
  beforeEach(() => {
    MockEventSource.instances = [];
    (globalThis as { EventSource: unknown }).EventSource = MockEventSource as unknown;
  });
  afterEach(() => { vi.restoreAllMocks(); });

  it('captures price events and builds history', async () => {
    const { result } = renderHook(() => useSSE('/test'));
    await act(async () => { await Promise.resolve(); });
    const es = MockEventSource.instances[0];

    act(() => {
      es.emit({ ticker: 'AAPL', price: 190.0, previous_price: 189.5, timestamp: '2026-04-18T12:00:00Z', direction: 'up' });
      es.emit({ ticker: 'AAPL', price: 191.0, previous_price: 190.0, timestamp: '2026-04-18T12:00:01Z', direction: 'up' });
    });

    expect(result.current.prices.AAPL.price).toBe(191.0);
    expect(result.current.priceHistory.AAPL.length).toBe(2);
    expect(result.current.priceHistory.AAPL[1].price).toBe(191.0);
  });

  it('transitions connectionState to open', async () => {
    const { result } = renderHook(() => useSSE('/test'));
    await act(async () => { await Promise.resolve(); });
    expect(result.current.connectionState).toBe('open');
  });
});
