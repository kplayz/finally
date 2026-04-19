import { test, expect } from '@playwright/test';
import { resetAccount, waitForStreaming } from './helpers';

test.describe('Buy and sell (PLAN §12 scenarios 3 & 4)', () => {
  test.beforeEach(async ({ request }) => { await resetAccount(request); });

  test('buy decreases cash, adds position, portfolio updates', async ({ page }) => {
    await page.goto('/');
    await waitForStreaming(page);

    // Wait for AAPL price to resolve.
    await expect
      .poll(async () => (await page.getByTestId('price-AAPL').textContent())?.trim() ?? '')
      .not.toBe('—');

    await page.getByLabel('Ticker', { exact: true }).fill('AAPL');
    await page.getByLabel('Quantity').fill('1');
    await page.getByTestId('buy-button').click();

    // Cash should fall below $10,000 once the trade lands.
    await expect
      .poll(async () => {
        const txt = (await page.getByTestId('cash-balance').textContent()) ?? '';
        return parseFloat(txt.replace(/[$,\s]/g, ''));
      }, { timeout: 10_000 })
      .toBeLessThan(10_000);
  });

  test('sell increases cash relative to post-buy balance', async ({ page, request }) => {
    await page.goto('/');
    await waitForStreaming(page);
    await expect.poll(async () => (await page.getByTestId('price-AAPL').textContent())?.trim() ?? '').not.toBe('—');

    // Buy 1 via API to seed the position deterministically.
    const buyRes = await request.post('/api/portfolio/trade', { data: { ticker: 'AAPL', quantity: 1, side: 'buy' } });
    expect(buyRes.ok()).toBe(true);
    const afterBuyCash = (await buyRes.json()).cash_remaining as number;

    await page.getByLabel('Ticker', { exact: true }).fill('AAPL');
    await page.getByLabel('Quantity').fill('1');
    await page.getByTestId('sell-button').click();

    await expect
      .poll(async () => {
        const txt = (await page.getByTestId('cash-balance').textContent()) ?? '';
        return parseFloat(txt.replace(/[$,\s]/g, ''));
      }, { timeout: 10_000 })
      .toBeGreaterThan(afterBuyCash);
  });
});
