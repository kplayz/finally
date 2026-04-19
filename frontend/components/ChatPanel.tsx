'use client';

import { useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import type { ChatResponse } from '@/lib/types';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  actions?: {
    trades: ChatResponse['trades'];
    watchlist_changes: ChatResponse['watchlist_changes'];
    errors: string[];
  };
}

interface Props {
  onActionsApplied: () => void;
}

export function ChatPanel({ onActionsApplied }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, loading]);

  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;
    const userMsg: Message = { role: 'user', content: text };
    setMessages((m) => [...m, userMsg]);
    setInput('');
    setLoading(true);
    try {
      const res = await api.sendChatMessage(text);
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: res.message,
          actions: {
            trades: res.trades,
            watchlist_changes: res.watchlist_changes,
            errors: res.errors,
          },
        },
      ]);
      if (res.trades.length || res.watchlist_changes.length) {
        onActionsApplied();
      }
    } catch (err) {
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: `Error: ${err instanceof Error ? err.message : 'unknown'}`,
          actions: { trades: [], watchlist_changes: [], errors: [] },
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="panel"
      style={{ gridArea: 'chat', display: 'flex', flexDirection: 'column' }}
      data-testid="chat-panel"
    >
      <div className="panel-title">FinAlly Assistant</div>
      <div
        ref={scrollRef}
        style={{ flex: 1, overflowY: 'auto', padding: 10, display: 'flex', flexDirection: 'column', gap: 10 }}
        data-testid="chat-messages"
      >
        {messages.length === 0 && (
          <div className="dim">Ask me about your portfolio or tell me to trade.</div>
        )}
        {messages.map((m, i) => (
          <div key={i} style={{ textAlign: m.role === 'user' ? 'right' : 'left' }}>
            <div
              style={{
                display: 'inline-block',
                padding: '6px 10px',
                borderRadius: 6,
                background: m.role === 'user' ? 'var(--panel-2)' : 'transparent',
                border: m.role === 'assistant' ? '1px solid var(--border)' : 'none',
                maxWidth: '90%',
              }}
            >
              <div style={{ whiteSpace: 'pre-wrap' }}>{m.content}</div>
              {m.actions && (m.actions.trades.length > 0 ||
                m.actions.watchlist_changes.length > 0 ||
                m.actions.errors.length > 0) && (
                <div style={{ marginTop: 6, fontSize: 11 }} data-testid="chat-actions">
                  {m.actions.trades.map((t, j) => (
                    <div key={`t${j}`} className={t.side === 'buy' ? 'up' : 'down'}>
                      ✓ {t.side.toUpperCase()} {t.quantity} {t.ticker} @ ${t.price.toFixed(2)}
                    </div>
                  ))}
                  {m.actions.watchlist_changes.map((w, j) => (
                    <div key={`w${j}`} className="dim">
                      · {w.action === 'add' ? 'Added' : 'Removed'} {w.ticker}
                    </div>
                  ))}
                  {m.actions.errors.map((err, j) => (
                    <div key={`e${j}`} className="down">✗ {err}</div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="dim" data-testid="chat-loading">…thinking</div>
        )}
      </div>
      <form onSubmit={send} style={{ display: 'flex', gap: 6, padding: 10, borderTop: '1px solid var(--border)' }}>
        <input
          aria-label="Chat message"
          placeholder="Ask or instruct…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={loading}
          style={{ flex: 1 }}
        />
        <button type="submit" className="btn-primary" disabled={loading || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
