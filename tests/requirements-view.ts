import { expect, type Page } from '@playwright/test';

export async function waitForRequirementsView(page: Page) {
  if (!(await page.locator('.req-explorer').count())) return;

  await expect(page.getByTestId('req-table')).toBeVisible();
}
