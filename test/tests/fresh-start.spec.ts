import { test, expect } from '@playwright/test';
import { resetAccount, waitForStreaming } from './helpers';

test.describe('Fresh start (PLAN §12 scenario 1)', () => {
  test.beforeEach(async ({ request }) => {
    await resetAccount(request);
  });

  test('default watchlist shown, $10k cash, prices streaming', async ({ page }) => {
    await page.goto('/');
    await waitForStreaming(page);

    const tickers = ['AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA', 'NVDA', 'META', 'JPM', 'V', 'NFLX'];
    for (const t of tickers) {
      await expect(page.getByTestId(`watchlist-row-${t}`)).toBeVisible();
    }

    await expect(page.getByTestId('cash-balance')).toHaveText(/10,000\.00/);

    // At least one price should resolve within 10s of streaming.
    await expect
      .poll(async () => (await page.getByTestId('price-AAPL').textContent())?.trim() ?? '', { timeout: 10_000 })
      .not.toBe('—');
  });
});
