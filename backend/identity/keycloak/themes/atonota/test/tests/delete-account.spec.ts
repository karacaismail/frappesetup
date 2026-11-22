import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { focusDiff } from './focus-diff';
import { ACCOUNT_DELETION_URL, createUser, ensureKeycloakDeleteActionOff, grantStockDeleteRole, KC, loginUrl, REALM, submitPassword, userExists } from './helpers';

// Account deletion path (project record O-27, contract section 7).
// - Keycloak's own "delete_account" action is switched off. It deletes the user in the first step.
// - The account console shows a link to the account deletion page of Press instead.
// - The address comes from a setting (IDENTITY_ACCOUNT_DELETION_URL).
// - Only a customer sees the link. A customer holds the realm role "request-account-deletion".
//   An invited employee does not hold it and never receives the link.
// - Keycloak's own "delete-account" role authorises Keycloak's delete action. The product grants it to nobody,
//   and it does not show the link.
// The server decides: the link is part of the page that Keycloak sends. It is not added or hidden in the browser.

const LINK = '#at-account-deletion-link';
const SECTION = '#at-account-deletion';

async function signIn(page: Page, options: { customer: boolean }): Promise<string> {
  const email = await createUser({ canDeleteAccount: options.customer });
  await ensureKeycloakDeleteActionOff();
  await page.goto(`${KC}/realms/${REALM}/account/`);
  await submitPassword(page, email);
  await expect(page.locator('#save-btn')).toBeVisible({ timeout: 20_000 });
  return email;
}

/** Returns the account console page exactly as the server sends it to this browser session, before any script runs. */
const serverPage = async (page: Page) => (await page.request.get(`${KC}/realms/${REALM}/account/`)).text();

/** Returns the caching header of the account console page. The page differs per user, so no cache may keep it. */
const serverCacheControl = async (page: Page) => (await page.request.get(`${KC}/realms/${REALM}/account/`)).headers()['cache-control'] ?? '';

const tabKey = (browserName: string) => (browserName === 'webkit' ? 'Alt+Tab' : 'Tab');

test('the test environment sets the address of the deletion page', () => {
  expect(ACCOUNT_DELETION_URL, 'IDENTITY_ACCOUNT_DELETION_URL is set in test/.env').toMatch(/^https?:\/\/.+/);
});

test('@matris customer: the personal info page shows a link to the account deletion page', async ({ page }) => {
  await signIn(page, { customer: true });
  const html = await serverPage(page);
  expect(html, 'the server sends the link').toContain(`id="at-account-deletion-link" href="${ACCOUNT_DELETION_URL}"`);
  // The page carries user-specific markup. A shared cache must never store it.
  expect(await serverCacheControl(page), 'the page is not cacheable').toMatch(/no-store|no-cache/);

  const section = page.locator(SECTION);
  const link = page.locator(LINK);
  await expect(section).toBeVisible();
  await expect(section).toContainText('Hesabınızı silmek mi istiyorsunuz?');
  await expect(link).toHaveText('Hesap silme sayfasına gidin');
  await expect(link).toHaveAttribute('href', ACCOUNT_DELETION_URL);
  await expect(page.getByRole('link', { name: 'Hesap silme sayfasına gidin' })).toBeVisible();

  const result = await page.evaluate(() => {
    const element = document.querySelector<HTMLElement>('#at-account-deletion')!;
    const anchor = document.querySelector<HTMLElement>('#at-account-deletion-link')!;
    const box = element.getBoundingClientRect();
    const texts = [element, ...element.querySelectorAll<HTMLElement>('*')].filter((node) => [...node.childNodes].some((child) => child.nodeType === Node.TEXT_NODE && child.textContent?.trim()));
    return {
      scroll: document.documentElement.scrollWidth,
      client: document.documentElement.clientWidth,
      left: box.left,
      right: box.right,
      bottom: box.bottom,
      viewport: innerHeight,
      small: texts.filter((node) => Number.parseFloat(getComputedStyle(node).fontSize) < 14).length,
      fonts: texts.map((node) => getComputedStyle(node).fontFamily).filter((family) => !/^"?Outfit/.test(family)),
      linkHeight: anchor.getBoundingClientRect().height,
      minimum: matchMedia('(any-pointer: coarse)').matches ? 48 : 44,
      saveVisible: document.querySelector('#save-btn')!.getBoundingClientRect().height > 0,
    };
  });
  // The section takes a row at the bottom. On a short screen the form must still be reachable by scrolling:
  // the save button can be brought fully into the area above the section.
  await page.locator('#save-btn').scrollIntoViewIfNeeded();
  const reach = await page.evaluate(() => {
    const save = document.querySelector('#save-btn')!.getBoundingClientRect();
    const section = document.querySelector('#at-account-deletion')!.getBoundingClientRect();
    return { saveBottom: save.bottom, saveTop: save.top, sectionTop: section.top };
  });
  expect(reach.saveBottom, 'the save button is not covered by the section').toBeLessThanOrEqual(reach.sectionTop + 1);
  expect(reach.saveTop, 'the save button is on screen').toBeGreaterThanOrEqual(0);

  // The section stays at the bottom of the screen, because it is outside the console application.
  // On a phone, upright or turned, it must be one compact row so it takes little of the screen.
  const viewport = page.viewportSize()!;
  const compact = viewport.width < 480 || viewport.height < 480;
  const sectionBox = (await page.locator(SECTION).boundingBox())!;
  if (compact) expect(sectionBox.height, 'compact section height on a phone').toBeLessThanOrEqual(56);
  expect(sectionBox.height / viewport.height, 'share of the screen height').toBeLessThanOrEqual(0.15);
  // The question stays available to a screen reader also when it is not drawn.
  await expect(page.locator(`${SECTION} .at-account-deletion__text`)).toHaveText('Hesabınızı silmek mi istiyorsunuz?');
  // There is clear space between the form buttons and the section when the page is scrolled to its end.
  await page.locator('#cancel-btn').evaluate((element) => element.scrollIntoView({ block: 'end' }));
  const gap = await page.evaluate(() => {
    const scroller = document.querySelector('.pf-v5-c-page__main')!;
    scroller.scrollTop = scroller.scrollHeight;
    return document.querySelector('#at-account-deletion')!.getBoundingClientRect().top - document.querySelector('#save-btn')!.getBoundingClientRect().bottom;
  });
  expect(gap, 'space between the buttons and the section').toBeGreaterThanOrEqual(16);
  expect(result.scroll, 'horizontal overflow').toBeLessThanOrEqual(result.client);
  expect(result.left, 'inside the viewport').toBeGreaterThanOrEqual(0);
  expect(result.right, 'inside the viewport').toBeLessThanOrEqual(result.client + 1);
  expect(result.bottom, 'inside the viewport').toBeLessThanOrEqual(result.viewport + 1);
  expect(result.small, 'text below 14px').toBe(0);
  expect(result.fonts, 'font other than Outfit').toEqual([]);
  expect(result.linkHeight, 'touch target').toBeGreaterThanOrEqual(result.minimum - 0.5);
  expect(result.saveVisible).toBe(true);
});

test('@matris employee: the server sends no deletion link and the page has none', async ({ page }) => {
  await signIn(page, { customer: false });
  const html = await serverPage(page);
  expect(html, 'server page for an employee').not.toContain('at-account-deletion');
  expect(html).not.toContain(ACCOUNT_DELETION_URL);
  await expect(page.locator(SECTION)).toHaveCount(0);
  await expect(page.locator(LINK)).toHaveCount(0);
  await expect(page.getByText(/Hesabınızı silmek|Hesap silme/)).toHaveCount(0);

  // The rest of the console still works for the employee.
  await page.locator('#firstName').fill('Calisan');
  await page.locator('#save-btn').click();
  await expect(page.locator('.pf-v5-c-alert.pf-m-success')).toBeVisible();
});

test('signed-out visitor: the server sends no deletion link', async ({ page }) => {
  const html = await serverPage(page);
  expect(html).not.toContain('at-account-deletion');
  expect(html).not.toContain(ACCOUNT_DELETION_URL);
});

test('the link shows on the personal info page only', async ({ page }) => {
  await signIn(page, { customer: true });
  await expect(page.locator(SECTION)).toBeVisible();
  for (const path of ['account-security/signing-in', 'account-security/device-activity', 'applications']) {
    await page.goto(`${KC}/realms/${REALM}/account/${path}`);
    await expect(page.locator('.pf-v5-c-page__main-section').first()).toBeVisible({ timeout: 20_000 });
    await expect(page.locator(SECTION), path).toBeHidden();
  }
  await page.goto(`${KC}/realms/${REALM}/account/`);
  await expect(page.locator(SECTION)).toBeVisible();
});

test('the link follows the page when the console changes pages without a page load', async ({ page }) => {
  await signIn(page, { customer: true });
  await expect(page.locator(SECTION)).toBeVisible();
  let loads = 0;
  page.on('load', () => (loads += 1));
  // The sidebar is collapsed on a narrow screen. The toggle opens it.
  const nav = page.getByRole('link', { name: 'Uygulamalar', exact: true });
  if (!(await nav.isVisible())) await page.locator('#nav-toggle').click();
  await nav.click();
  await expect(page).toHaveURL(/\/account\/applications/);
  await expect(page.locator(SECTION)).toBeHidden();
  const back = page.getByRole('link', { name: 'Kişisel bilgiler', exact: true });
  if (!(await back.isVisible())) await page.locator('#nav-toggle').click();
  await back.click();
  await expect(page.locator('#save-btn')).toBeVisible();
  await expect(page.locator(SECTION)).toBeVisible();
  expect(loads, 'the console changed pages without a page load').toBe(0);
});

test('an open menu does not change the page layout', async ({ page }) => {
  await signIn(page, { customer: true });
  const measure = () =>
    page.evaluate(() => ({
      app: Math.round(document.querySelector('#app')!.getBoundingClientRect().height),
      section: Math.round(document.querySelector('#at-account-deletion')!.getBoundingClientRect().top),
      scroll: document.documentElement.scrollHeight,
    }));
  const before = await measure();
  await page.locator('[id="attributes.locale"]').click();
  await expect(page.locator('.pf-v5-c-menu:visible').first()).toBeVisible();
  expect(await measure(), 'layout with an open menu').toEqual(before);
});

test('customer with English as the language reads the link in English', async ({ page }) => {
  const email = await createUser({ canDeleteAccount: true, locale: 'en' });
  await ensureKeycloakDeleteActionOff();
  await page.goto(`${KC}/realms/${REALM}/account/`);
  await submitPassword(page, email);
  await expect(page.locator('#save-btn')).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(SECTION)).toContainText('Do you want to delete your account?');
  await expect(page.locator(LINK)).toHaveText('Go to the account deletion page');
});

test('customer: the link is reached with the keyboard and shows the focus line', async ({ page, browserName }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await signIn(page, { customer: true });
  await page.addStyleTag({ content: '* { caret-color: transparent !important; }' });
  await page.locator('#cancel-btn').focus();
  await page.keyboard.press(tabKey(browserName));
  const link = page.locator(LINK);
  await expect(link).toBeFocused();
  expect(await link.evaluate((element) => getComputedStyle(element).outlineStyle === 'none' || getComputedStyle(element).outlineWidth === '0px')).toBe(true);
  const { diff, rect } = await focusDiff(page, link);
  expect(diff.count, 'visible focus indicator').toBeGreaterThanOrEqual(24);
  expect(diff.contrast, 'indicator contrast').toBeGreaterThanOrEqual(3);
  expect(diff.minY, 'no line on the top edge').toBeGreaterThanOrEqual(rect.top + rect.height / 2);
  expect(diff.maxY - diff.minY, 'one straight line').toBeLessThanOrEqual(6);
});

test('customer: the link leads to the configured deletion page', async ({ page }) => {
  await signIn(page, { customer: true });
  // The deletion page belongs to Press. It is not part of this test environment, so the address is answered here.
  await page.route(`${ACCOUNT_DELETION_URL}**`, (route) => route.fulfill({ status: 200, contentType: 'text/html', body: '<h1>stub deletion page</h1>' }));
  await page.locator(LINK).click();
  await expect(page).toHaveURL(ACCOUNT_DELETION_URL);
  await expect(page.locator('h1')).toHaveText('stub deletion page');
});

for (const scheme of ['light', 'dark'] as const) {
  test(`customer: the page with the deletion link passes axe (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' });
    await signIn(page, { customer: true });
    if (scheme === 'dark') await expect(page.locator('html')).toHaveClass(/pf-v5-theme-dark/);
    await expect(page.locator(SECTION)).toBeVisible();
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice']).analyze();
    expect(results.violations.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(' ')).join(' | ')}`)).toEqual([]);
  });
}

test("Keycloak's own delete action stays off, also for a customer", async ({ page }) => {
  const email = await signIn(page, { customer: true });
  const html = await serverPage(page);
  expect(/"deleteAccountAllowed":\s*false/.test(html), 'the stock delete feature is off in the server page').toBe(true);
  await expect(page.locator('[data-testid="delete-account"]')).toHaveCount(0);
  await expect(page.locator('#delete-account-btn')).toHaveCount(0);

  // A direct request for the Keycloak action does not open a delete confirmation and deletes nothing.
  await page.context().clearCookies();
  await page.goto(`${loginUrl()}&kc_action=delete_account`);
  await submitPassword(page, email);
  await expect(page.locator('#save-btn, #kc-error-message').first()).toBeVisible({ timeout: 20_000 });
  await expect(page.locator('#kc-deleteaccount-form')).toHaveCount(0);
  expect(await userExists(email)).toBe(true);
});

test("Keycloak's own delete-account role does not show the link", async ({ page }) => {
  // The customer marker is a separate role. Granting Keycloak's role alone must change nothing.
  const email = await createUser();
  await grantStockDeleteRole(email);
  await ensureKeycloakDeleteActionOff();
  await page.goto(`${KC}/realms/${REALM}/account/`);
  await submitPassword(page, email);
  await expect(page.locator('#save-btn')).toBeVisible({ timeout: 20_000 });
  expect(await serverPage(page)).not.toContain('at-account-deletion');
  await expect(page.locator(SECTION)).toHaveCount(0);
});

// Unsafe and missing addresses are checked in the image build, without a browser:
// account-provider/src/test/java/platform/identity/account/AccountDeletionLinkConsoleCheck.java

// Produces screenshots for an independent review. Runs only with VISUAL=1.
for (const scheme of ['light', 'dark'] as const) {
  test(`account deletion link screenshot (${scheme})`, async ({ page, browserName }, info) => {
    test.skip(!process.env.VISUAL, 'Screenshots are produced only with VISUAL=1');
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' });
    await signIn(page, { customer: true });
    const out = `referans/${info.project.name}/`;
    await page.screenshot({ path: `${out}account-deletion-link-${scheme}.png` });
    await page.locator('#cancel-btn').focus();
    await page.keyboard.press(tabKey(browserName));
    await page.screenshot({ path: `${out}account-deletion-link-focus-${scheme}.png` });
    // A phone turned sideways: the shortest screen the section has to share.
    await page.setViewportSize({ width: 667, height: 375 });
    await page.screenshot({ path: `${out}account-deletion-link-landscape-${scheme}.png` });
  });
}
