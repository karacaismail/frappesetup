import { expect, test } from '@playwright/test';
import { createUser, KC, keycloakDeleteActionEnabled, loginUrl, REALM, setKeycloakDeleteAction, submitPassword, userExists } from './helpers';

// These tests change a realm-wide setting, so they run alone, before every other project (see playwright.config.ts).
// The contract keeps Keycloak's "delete_account" action off. This file proves what the account console
// provider does if somebody switches the action on by mistake.

test.describe.configure({ mode: 'serial' });

test.afterAll(async () => {
  await setKeycloakDeleteAction(false);
});

test('with the Keycloak delete action switched on, the console still does not offer it', async ({ page }) => {
    const email = await createUser({ customer: true });
  await setKeycloakDeleteAction(true);
  try {
    // The stock console would now show its delete section to every user of the console.
    await page.goto(`${KC}/realms/${REALM}/account/`);
    await submitPassword(page, email);
    await expect(page.locator('#save-btn')).toBeVisible({ timeout: 20_000 });
    expect(await keycloakDeleteActionEnabled(), 'the realm action is on while this test looks').toBe(true);
    const html = await (await page.request.get(`${KC}/realms/${REALM}/account/`)).text();
    expect(/"deleteAccountAllowed":\s*false/.test(html), 'the provider keeps the stock delete feature off').toBe(true);
    await expect(page.locator('[data-testid="delete-account"]')).toHaveCount(0);
    await expect(page.locator('#delete-account-btn')).toHaveCount(0);
    // The customer still gets the link to the deletion page of the product.
    await expect(page.locator('#at-account-deletion-link')).toBeVisible();
  } finally {
    await setKeycloakDeleteAction(false);
  }
});

test('with the Keycloak delete action switched on, a customer cannot delete the account in Keycloak', async ({ page }) => {
  const email = await createUser({ customer: true });
  await setKeycloakDeleteAction(true);
  try {
    // The customer role is not Keycloak's "delete-account" role, so Keycloak refuses its own delete action.
    await page.goto(`${loginUrl()}&kc_action=delete_account`);
    await submitPassword(page, email);
    // The refusal must be Keycloak's "not allowed to delete" answer, not just any error screen.
    await expect(page.locator('#kc-error-message')).toContainText('Bu hesabı silme izniniz yok.', { timeout: 20_000 });
    await expect(page.locator('#kc-deleteaccount-form')).toHaveCount(0);
    await expect(page.locator('#kc-submit')).toHaveCount(0);
    expect(await userExists(email), 'the account stays').toBe(true);
  } finally {
    await setKeycloakDeleteAction(false);
  }
});
