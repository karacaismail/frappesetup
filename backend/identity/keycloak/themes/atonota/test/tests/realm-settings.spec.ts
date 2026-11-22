import { expect, test } from '@playwright/test';
import { createUser, ensureMisconfiguredRealm, KC, keycloakDeleteActionEnabled, loginUrl, MISCONFIGURED_REALM, REALM, submitPassword, userExists } from './helpers';

// The contract keeps Keycloak's "delete_account" action off. This file proves what happens if somebody
// switches the action on by mistake. The mistake lives in a second realm made for it. The test realm is
// never changed, so no test can repair or hide a wrong setting in it.

test.beforeAll(async () => {
  await ensureMisconfiguredRealm();
});

test('the wrongly configured realm has the delete action on and the test realm is untouched', async () => {
  expect(await keycloakDeleteActionEnabled(MISCONFIGURED_REALM), 'action in the wrongly configured realm').toBe(true);
  expect(await keycloakDeleteActionEnabled(REALM), 'action in the test realm, as the realm file installed it').toBe(false);
});

test('with the Keycloak delete action switched on, the console still does not offer it', async ({ page }) => {
  const email = await createUser({ customer: true, realm: MISCONFIGURED_REALM });
  // The stock console would now show its delete section to every user of the console.
  await page.goto(`${KC}/realms/${MISCONFIGURED_REALM}/account/`);
  await submitPassword(page, email);
  await expect(page.locator('#save-btn')).toBeVisible({ timeout: 20_000 });
  const html = await (await page.request.get(`${KC}/realms/${MISCONFIGURED_REALM}/account/`)).text();
  expect(/"deleteAccountAllowed":\s*false/.test(html), 'the provider keeps the stock delete feature off').toBe(true);
  await expect(page.locator('[data-testid="delete-account"]')).toHaveCount(0);
  await expect(page.locator('#delete-account-btn')).toHaveCount(0);
  // The customer still gets the link to the deletion page of the product.
  await expect(page.locator('#at-account-deletion-link')).toBeVisible();
});

test('with the Keycloak delete action switched on, a customer cannot delete the account in Keycloak', async ({ page }) => {
  const email = await createUser({ customer: true, realm: MISCONFIGURED_REALM });
  // The customer role is not Keycloak's "delete-account" role, so Keycloak refuses its own delete action.
  await page.goto(`${loginUrl(undefined, MISCONFIGURED_REALM)}&kc_action=delete_account`);
  await submitPassword(page, email);
  // The refusal must be Keycloak's "not allowed to delete" answer, not just any error screen.
  await expect(page.locator('#kc-error-message')).toContainText('Bu hesabı silme izniniz yok.', { timeout: 20_000 });
  await expect(page.locator('#kc-deleteaccount-form')).toHaveCount(0);
  await expect(page.locator('#kc-submit')).toHaveCount(0);
  expect(await userExists(email, MISCONFIGURED_REALM), 'the account stays').toBe(true);
});
