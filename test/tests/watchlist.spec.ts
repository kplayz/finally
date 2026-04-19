import { test, expect } from '@playwright/test';
import { resetAccount, waitForStreaming } from './helpers';

test.describe('Watchlist add/remove (PLAN §12 scenario 2)', () => {
  test.beforeEach(async ({ request }) => { await resetAccount(request); });

  test('add and remove a ticker', async ({ page }) => {
    await page.goto('/');
    await waitForStreaming(page);

    await page.getByLabel('Add ticker').fill('AMD');
    await page.getByRole('button', { name: 'Add' }).click();

    await expect(page.getByTestId('watchlist-row-AMD')).toBeVisible();

    await page.getByRole('button', { name: 'Remove AMD' }).click();
    await expect(page.getByTestId('watchlist-row-AMD')).toHaveCount(0);
  });
});
