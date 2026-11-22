import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { focusDiff } from './focus-diff';
import { createUser, enableDeleteAccount, KC, loginUrl, PASSWORD, REALM, submitPassword, userExists } from './helpers';

// Account deletion path (project record O-27): the account console shows a delete section,
// and the confirmation screen of the login theme finishes the request.

/** Signs in a user who may delete the own account and opens the personal info page. */
async function openPersonalInfo(page: Page): Promise<string> {
  const email = await createUser({ canDeleteAccount: true });
  await page.goto(`${KC}/realms/${REALM}/account/`);
  await submitPassword(page, email);
  await expect(page.locator('#save-btn')).toBeVisible();
  return email;
}

const openSection = async (page: Page) => {
  const toggle = page.locator('[data-testid="delete-account"] .pf-v5-c-expandable-section__toggle');
  await toggle.click();
  await expect(page.locator('#delete-account-btn')).toBeVisible();
};

/** Keycloak may ask for the password again before a sensitive action. This helper handles both paths. */
async function reachConfirmation(page: Page): Promise<void> {
  await expect(page.locator('#kc-form-login, #kc-deleteaccount-form').first()).toBeVisible();
  if (await page.locator('#kc-form-login').isVisible()) {
    await page.locator('#password').fill(PASSWORD);
    await page.locator('#kc-login').click();
  }
  await expect(page.locator('#kc-deleteaccount-form')).toBeVisible();
}

const tabKey = (browserName: string) => (browserName === 'webkit' ? 'Alt+Tab' : 'Tab');

test('@matris account: the delete account section is visible and fits the screen', async ({ page }) => {
  await openPersonalInfo(page);
  const section = page.locator('[data-testid="delete-account"]');
  await expect(section).toBeVisible();
  await expect(section.locator('.pf-v5-c-expandable-section__toggle')).toHaveText('Hesabı silin');
  await openSection(page);

  // The warning says what really happens (O-27): the account is deleted, work records stay without the name.
  await expect(section.locator('.pf-v5-c-alert')).toContainText('Hesabınız kalıcı olarak silinir.');
  await expect(section.locator('.pf-v5-c-alert')).toContainText('İş kayıtlarınız silinmez.');
  await expect(page.locator('#delete-account-btn')).toHaveText('Silin');

  const result = await page.evaluate(() => {
    const beyond = [...document.querySelectorAll<HTMLElement>('[data-testid="delete-account"] *')]
      .filter((element) => element.checkVisibility())
      .filter((element) => element.getBoundingClientRect().right > innerWidth + 1)
      .map((element) => element.className);
    const small = [...document.querySelectorAll<HTMLElement>('[data-testid="delete-account"] *')]
      .filter((element) => element.checkVisibility() && element.childNodes.length > 0)
      .filter((element) => [...element.childNodes].some((node) => node.nodeType === Node.TEXT_NODE && node.textContent?.trim()))
      .filter((element) => Number.parseFloat(getComputedStyle(element).fontSize) < 14)
      .map((element) => element.className);
    const min = matchMedia('(any-pointer: coarse)').matches ? 48 : 44;
    const targets = [...document.querySelectorAll<HTMLElement>('[data-testid="delete-account"] button')]
      .filter((element) => element.checkVisibility())
      .filter((element) => element.getBoundingClientRect().height < min - 0.5)
      .map((element) => `${element.id} ${Math.round(element.getBoundingClientRect().height)}`);
    return { beyond, small, targets };
  });
  expect(result.beyond, 'element beyond the viewport edge').toEqual([]);
  expect(result.small, 'text below 14px').toEqual([]);
  expect(result.targets, 'small touch target').toEqual([]);
});

test('account: the delete section works with the keyboard and shows the focus line', async ({ page, browserName }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await openPersonalInfo(page);
  await page.addStyleTag({ content: '* { caret-color: transparent !important; }' });
  const toggle = page.locator('[data-testid="delete-account"] .pf-v5-c-expandable-section__toggle');
  await page.locator('#cancel-btn').focus();
  await page.keyboard.press(tabKey(browserName));
  await expect(toggle).toBeFocused();
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  for (const target of [toggle]) {
    await target.evaluate((element) => element.scrollIntoView({ block: 'center' }));
    const { diff, rect } = await focusDiff(page, target);
    expect(diff.count, 'visible focus indicator on the toggle').toBeGreaterThanOrEqual(24);
    expect(diff.minY, 'no line on the top edge').toBeGreaterThanOrEqual(rect.top + rect.height / 2);
  }
  await page.keyboard.press('Enter');
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await page.keyboard.press(tabKey(browserName));
  const button = page.locator('#delete-account-btn');
  await expect(button).toBeFocused();
  await button.evaluate((element) => element.scrollIntoView({ block: 'center' }));
  const { diff, rect } = await focusDiff(page, button);
  expect(diff.count, 'visible focus indicator on the delete button').toBeGreaterThanOrEqual(24);
  expect(diff.minY, 'no line on the top edge').toBeGreaterThanOrEqual(rect.top + rect.height / 2);
  expect(diff.maxY - diff.minY, 'one straight line').toBeLessThanOrEqual(6);
});

for (const scheme of ['light', 'dark'] as const) {
  test(`account: delete section passes axe (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' });
    await openPersonalInfo(page);
    if (scheme === 'dark') await expect(page.locator('html')).toHaveClass(/pf-v5-theme-dark/);
    await openSection(page);
    const results = await new AxeBuilder({ page })
      .include('[data-testid="delete-account"]')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'])
      .analyze();
    // No rule is waived. The theme script gives the stock alert title the right heading level.
    expect(results.violations.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(' ')).join(' | ')}`)).toEqual([]);
  });
}

// Project record O-27: only a customer may delete the own account. An employee is invited and must not see the path.
// A customer holds the "delete-account" role of the "account" client. An employee does not.
// The decision is made on the server: the page that Keycloak sends to an employee has the feature switched off,
// so the console never creates the section. Hiding it with CSS would not be enough.

/** Reads the feature flag from the page that the server sent, before any script runs. */
async function serverSaysDeleteAllowed(page: Page): Promise<boolean> {
  const html = await (await page.request.get(`${KC}/realms/${REALM}/account/`)).text();
  const json = html.slice(html.indexOf('<script id="environment"'));
  const match = /"deleteAccountAllowed":\s*(true|false)/.exec(json);
  expect(match, 'the page carries the deleteAccountAllowed flag').not.toBeNull();
  return match![1] === 'true';
}

test('@matris employee: the server switches the delete feature off and the section is never created', async ({ page }) => {
  // An employee can use the account console (default roles, including "manage-account") but has no "delete-account" role.
  const email = await createUser();
  await enableDeleteAccount();
  await page.goto(`${KC}/realms/${REALM}/account/`);
  await submitPassword(page, email);
  await expect(page.locator('#save-btn')).toBeVisible();

  expect(await serverSaysDeleteAllowed(page), 'server flag for an employee').toBe(false);
  await expect(page.locator('[data-testid="delete-account"]')).toHaveCount(0);
  await expect(page.locator('#delete-account-btn')).toHaveCount(0);
  await expect(page.getByText('Hesabı silin')).toHaveCount(0);

  // The rest of the console still works for the employee.
  await page.locator('#firstName').fill('Calisan');
  await page.locator('#save-btn').click();
  await expect(page.locator('.pf-v5-c-alert.pf-m-success')).toBeVisible();
});

test('customer: the server switches the delete feature on', async ({ page }) => {
  await openPersonalInfo(page);
  expect(await serverSaysDeleteAllowed(page), 'server flag for a customer').toBe(true);
  await expect(page.locator('[data-testid="delete-account"]')).toHaveCount(1);
});

test('signed-out visitor: the server keeps the delete feature off', async ({ page }) => {
  await enableDeleteAccount();
  expect(await serverSaysDeleteAllowed(page)).toBe(false);
});

test('employee: a direct delete request is refused and the account stays', async ({ page }) => {
  const email = await createUser();
  await enableDeleteAccount();
  // The employee skips the console and asks Keycloak for the delete action directly.
  await page.goto(`${loginUrl()}&kc_action=delete_account`);
  await submitPassword(page, email);
  await expect(page.locator('#kc-error-message')).toContainText('Bu hesabı silme izniniz yok.');
  await expect(page.locator('#kc-deleteaccount-form')).toHaveCount(0);
  expect(await userExists(email)).toBe(true);
});

for (const scheme of ['light', 'dark'] as const) {
  test(`delete confirmation screen (${scheme}): the deleting button takes its colour from the shared danger token`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' });
    await openPersonalInfo(page);
    if (scheme === 'dark') await expect(page.locator('html')).toHaveClass(/pf-v5-theme-dark/);
    await openSection(page);
    const resolve = (target: Page) =>
      target.evaluate(() => {
        const probe = document.createElement('span');
        document.body.append(probe);
        probe.style.backgroundColor = 'var(--at-color-danger)';
        const danger = getComputedStyle(probe).backgroundColor;
        probe.style.backgroundColor = 'var(--at-color-action)';
        const action = getComputedStyle(probe).backgroundColor;
        probe.remove();
        return { danger, action };
      });
    // The console button and the final button use the same token, so both show the same colour.
    const consoleTokens = await resolve(page);
    const consoleButton = await page.locator('#delete-account-btn').evaluate((element) => getComputedStyle(element).backgroundColor);
    expect(consoleButton, 'console delete button').toBe(consoleTokens.danger);
    await page.locator('#delete-account-btn').click();
    await reachConfirmation(page);
    if (scheme === 'dark') await expect(page.locator('html')).toHaveClass(/pf-v5-theme-dark/);
    const tokens = await resolve(page);
    const submit = await page.locator('#kc-submit').evaluate((element) => getComputedStyle(element).backgroundColor);
    expect(tokens.danger, 'the two themes share the danger token').toBe(consoleTokens.danger);
    expect(submit, 'final delete button').toBe(tokens.danger);
    expect(submit).not.toBe(tokens.action);
    await expect(page.locator('#kc-cancel')).toBeVisible();
  });
}

test('@matris delete confirmation screen: plain Turkish, no overflow, readable text', async ({ page }) => {
  await openPersonalInfo(page);
  await openSection(page);
  await page.locator('#delete-account-btn').click();
  await reachConfirmation(page);
  await expect(page.locator('#kc-page-title')).toHaveText('Hesabınızı silin');
  await expect(page.locator('#kc-deleteaccount-form')).toContainText('Bu işlem geri alınamaz.');
  await expect(page.locator('#kc-deleteaccount-form')).toContainText('İş kayıtlarınız silinmez.');
  await expect(page.locator('#kc-submit')).toHaveText('Silmeyi onaylayın');
  await expect(page.locator('#kc-cancel')).toHaveText('Vazgeçin');
  // The deleting button uses the danger colour, like the delete button in the console.
  // It must not look like the safe primary action.
  const colours = await page.evaluate(() => {
    const probe = document.createElement('span');
    document.body.append(probe);
    const resolve = (token: string) => {
      probe.style.backgroundColor = `var(${token})`;
      return getComputedStyle(probe).backgroundColor;
    };
    const result = {
      submit: getComputedStyle(document.querySelector('#kc-submit')!).backgroundColor,
      danger: resolve('--at-color-danger'),
      action: resolve('--at-color-action'),
    };
    probe.remove();
    return result;
  });
  expect(colours.submit, 'the deleting button has the danger colour').toBe(colours.danger);
  expect(colours.submit).not.toBe(colours.action);
  const size = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
    small: [...document.querySelectorAll<HTMLElement>('#kc-deleteaccount-form *, #kc-page-title')]
      .filter((element) => element.checkVisibility() && [...element.childNodes].some((node) => node.nodeType === Node.TEXT_NODE && node.textContent?.trim()))
      .filter((element) => Number.parseFloat(getComputedStyle(element).fontSize) < 14).length,
    buttons: [...document.querySelectorAll<HTMLElement>('#kc-deleteaccount-form button')].map((element) => Math.round(element.getBoundingClientRect().height)),
  }));
  expect(size.scroll, 'horizontal overflow').toBeLessThanOrEqual(size.client);
  expect(size.small, 'text below 14px').toBe(0);
  expect(Math.min(...size.buttons), 'button height').toBeGreaterThanOrEqual(44);
  const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice']).analyze();
  expect(results.violations.map((violation) => violation.id)).toEqual([]);
});

test('delete flow: cancel keeps the account, confirm deletes it', async ({ page }) => {
  const email = await openPersonalInfo(page);
  const start = async () => {
    await openSection(page);
    await page.locator('#delete-account-btn').click();
    await reachConfirmation(page);
  };
  await start();
  await page.locator('#kc-cancel').click();
  await expect(page.locator('#save-btn')).toBeVisible();
  expect(await userExists(email), 'the account stays after cancel').toBe(true);

  await start();
  await page.locator('#kc-submit').click();
  await expect.poll(() => userExists(email), { message: 'the account is deleted after confirm' }).toBe(false);
});

// Produces screenshots for an independent review. Runs only with VISUAL=1.
for (const scheme of ['light', 'dark'] as const) {
  test(`delete account screenshot (${scheme})`, async ({ page }, info) => {
    test.skip(!process.env.VISUAL, 'Screenshots are produced only with VISUAL=1');
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' });
    await openPersonalInfo(page);
    await openSection(page);
    const out = `referans/${info.project.name}/`;
    await page.locator('[data-testid="delete-account"]').evaluate((element) => element.scrollIntoView({ block: 'center' }));
    await page.screenshot({ path: `${out}delete-account-section-${scheme}.png` });
    await page.locator('#delete-account-btn').click();
    await reachConfirmation(page);
    await page.screenshot({ path: `${out}delete-account-confirm-${scheme}.png`, fullPage: true });
  });
}
