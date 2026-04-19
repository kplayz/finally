import { test, expect } from '@playwright/test';
import { resetAccount, waitForStreaming } from './helpers';

test.describe('Portfolio visualization (PLAN §12 scenario 5)', () => {
  test.beforeEach(async ({ request }) => { await resetAccount(request); });

  test('heatmap renders after a trade and P&L chart accrues data', async ({ page, request }) => {
    // Seed a trade so the heatmap has something to render.
    const r = await request.post('/api/portfolio/trade', { data: { ticker: 'AAPL', quantity: 2, side: 'buy' } });
    expect(r.ok()).toBe(true);

    await page.goto('/');
    await waitForStreaming(page);

    // The Portfolio panel should include a Recharts treemap SVG with at least one <rect>.
    const heatmapRects = page.locator('.recharts-wrapper svg rect');
    await expect(heatmapRects.first()).toBeVisible({ timeout: 10_000 });

    // History endpoint must have at least one snapshot (immediate after-trade snapshot).
    const hist = await request.get('/api/portfolio/history');
    const body = await hist.json();
    expect(Array.isArray(body.snapshots)).toBe(true);
    expect(body.snapshots.length).toBeGreaterThanOrEqual(1);
  });
});
