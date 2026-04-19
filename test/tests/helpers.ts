import type { Page, APIRequestContext } from '@playwright/test';

export async function resetAccount(request: APIRequestContext): Promise<void> {
  const res = await request.post('/api/reset');
  if (!res.ok()) throw new Error(`reset failed: ${res.status()}`);
}

export async function waitForStreaming(page: Page) {
  // The header shows "open" when SSE is connected.
  await page.waitForSelector('[data-testid="connection-status"][data-state="open"]', { timeout: 15_000 });
}
