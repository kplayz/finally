import { test, expect } from '@playwright/test';
import { resetAccount, waitForStreaming } from './helpers';

test.describe('AI chat in mock mode (PLAN §12 scenario 6)', () => {
  test.beforeEach(async ({ request }) => { await resetAccount(request); });

  test('chat buy triggers inline trade confirmation', async ({ page }) => {
    await page.goto('/');
    await waitForStreaming(page);
    await expect.poll(async () => (await page.getByTestId('price-AAPL').textContent())?.trim() ?? '').not.toBe('—');

    await page.getByLabel('Chat message').fill('buy 3 AAPL');
    await page.getByRole('button', { name: 'Send' }).click();

    // Inline action confirmation appears.
    const actions = page.getByTestId('chat-actions').first();
    await expect(actions).toContainText('BUY 3 AAPL', { timeout: 10_000 });

    // Position should reflect in the portfolio.
    await expect
      .poll(async () => {
        const res = await page.request.get('/api/portfolio');
        return ((await res.json()).positions as { ticker: string; quantity: number }[]).find(p => p.ticker === 'AAPL')?.quantity ?? 0;
      }, { timeout: 10_000 })
      .toBe(3);
  });
});
