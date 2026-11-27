import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, test, type Page } from '@playwright/test';
import { createUser, KC, loginUrl, openLogin, REALM, screen, submitPassword } from './helpers';

// Security checks of the themes (frontend standard GV-1..GV-8, security requirements: XSS tests).
// The themes add no endpoint and no data access. They only render what Keycloak provides.

const themeRoot = fileURLToPath(new URL('../../', import.meta.url));
const sourceFiles = (pattern: RegExp): string[] => {
  const files: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const path = join(dir, entry);
      if (statSync(path).isDirectory()) walk(path);
      else if (pattern.test(entry)) files.push(path);
    }
  };
  for (const part of ['login', 'email', 'account']) walk(join(themeRoot, part));
  return files;
};

/** Java sources of the account console provider. */
const providerSources = (): string[] => {
  const files: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const path = join(dir, entry);
      if (statSync(path).isDirectory()) walk(path);
      else if (/\.java$/.test(entry)) files.push(path);
    }
  };
  walk(join(themeRoot, 'account-provider', 'src', 'main'));
  return files;
};

/** Collects console errors and CSP violations while a page is used. */
function watch(page: Page): string[] {
  const problems: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error') problems.push(`console: ${message.text()}`);
  });
  page.on('pageerror', (error) => problems.push(`pageerror: ${error.message}`));
  return problems;
}

test('GV-6: pages are served with a content security policy and the themes work under it', async ({ page }) => {
  const problems = watch(page);
  const violations: string[] = [];
  await page.addInitScript(() => {
    document.addEventListener('securitypolicyviolation', (event) => {
      (window as unknown as { cspViolations: string[] }).cspViolations ??= [];
      (window as unknown as { cspViolations: string[] }).cspViolations.push(`${event.violatedDirective} ${event.blockedURI}`);
    });
  });
  const response = await page.goto(loginUrl());
  const login = response!.headers();
  expect(login['content-security-policy']).toContain("frame-ancestors 'self'");
  expect(login['content-security-policy']).toContain("object-src 'none'");
  expect(login['x-content-type-options']).toBe('nosniff');
  expect(login['x-frame-options']).toBe('SAMEORIGIN');
  await expect(page.getByRole('button', { name: 'Giriş yap', exact: true })).toBeVisible();
  violations.push(...(await page.evaluate(() => (window as unknown as { cspViolations?: string[] }).cspViolations ?? [])));

  const email = await createUser();
  const account = await page.goto(`${KC}/realms/${REALM}/account/`);
  await submitPassword(page, email);
  await expect(page.locator('#save-btn')).toBeVisible();
  const console = await (await page.request.get(`${KC}/realms/${REALM}/account/`)).headers();
  expect(console['content-security-policy']).toContain("frame-ancestors 'self'");
  expect(account).not.toBeNull();
  violations.push(...(await page.evaluate(() => (window as unknown as { cspViolations?: string[] }).cspViolations ?? [])));

  expect(violations, 'content security policy violations').toEqual([]);
  expect(problems, 'console errors').toEqual([]);
});

test('XSS: markup typed into the sign-in form is shown as text and never runs', async ({ page }) => {
  const problems = watch(page);
  const payload = '"><img src=x onerror="window.__xss=1"><script>window.__xss=2</script>';
  await openLogin(page);
  await page.getByLabel('E-posta').fill(payload);
  await page.getByLabel('Parola', { exact: true }).fill('wrong-password-123');
  await page.getByRole('button', { name: 'Giriş yap', exact: true }).click();
  await expect(page.locator('#input-error-username')).toBeVisible();
  // The value comes back in the field. It must be text, not markup.
  await expect(page.getByLabel('E-posta')).toHaveValue(payload);
  expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined();
  expect(await page.locator('img[src="x"]').count()).toBe(0);
  expect(problems.filter((item) => item.startsWith('pageerror'))).toEqual([]);
});

test('XSS: markup in a profile name is shown as text in the theme screens', async ({ page }) => {
  // Registration writes the name. The password reset and account screens show data of the user.
  await screen('register').open(page);
  const email = `xss-${Date.now()}@example.test`;
  const name = '<img src=x onerror="window.__xss=3">';
  // The stock labels of this form carry a required mark, so the fields are addressed by their stable ids.
  await page.locator('#email').fill(email);
  await page.locator('#password').fill('long-sample-password-1');
  await page.locator('#password-confirm').fill('long-sample-password-1');
  await page.locator('#firstName').fill(name);
  await page.locator('#lastName').fill('Sample');
  await page.locator('#kc-register-form [type=submit]').click();
  // Keycloak either rejects the characters with a message or stores them. Neither path may run the markup.
  await expect(page.locator('#save-btn, #input-error-firstName').first()).toBeVisible();
  expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined();
  expect(await page.locator('img[src="x"]').count()).toBe(0);
});

test('GV-4: the login theme writes nothing to browser storage', async ({ page }) => {
  await openLogin(page);
  await page.keyboard.press('Tab');
  const stored = await page.evaluate(() => ({ local: Object.keys(localStorage), session: Object.keys(sessionStorage) }));
  expect(stored.local).toEqual([]);
  expect(stored.session).toEqual([]);
});

test('GV-1, GV-2, GV-7: theme scripts hold no secret, no HTML injection and no console output', () => {
  for (const file of sourceFiles(/\.js$/)) {
    const code = readFileSync(file, 'utf8').replace(/\/\/.*$/gm, '');
    expect(code, `${file}: innerHTML`).not.toMatch(/innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(|new Function/);
    expect(code, `${file}: console output`).not.toMatch(/console\.(log|debug|info|warn|error)/);
    expect(code, `${file}: storage`).not.toMatch(/localStorage|sessionStorage|document\.cookie|indexedDB/);
    // One request is allowed: the account script reads the theme message bundle from the same server.
    const requests = code.match(/fetch\([^)]*\)/g) ?? [];
    expect(requests.filter((call) => !call.startsWith('fetch(messagesUrl')), `${file}: network`).toEqual([]);
    expect(code, `${file}: network`).not.toMatch(/XMLHttpRequest|sendBeacon|WebSocket|import\(/);
    if (requests.length > 0) expect(code, `${file}: the bundle address is built from the server page data`).toContain('const messagesUrl = `${environment.serverBaseUrl}/resources/${environment.realm}/account/${environment.locale}`;');
  }
  for (const file of [...sourceFiles(/\.(ftl|properties|css|js|svg)$/), ...providerSources()]) {
    const text = readFileSync(file, 'utf8');
    expect(text, `${file}: secret-like value`).not.toMatch(/(api[_-]?key|secret|token|password)\s*[=:]\s*["']?[A-Za-z0-9+/_-]{16,}/i);
    expect(text, `${file}: external address`).not.toMatch(/(src|href|url\()\s*=?\s*["'(]?\s*(https?:)?\/\/(?!www\.w3\.org)/i);
  }
});

test('GV-2: templates never switch off escaping for user or realm data', () => {
  const allowed = new Set<string>([
    // Stock markup of Keycloak 26.8.2 template.ftl. The theme copy does not use it any more.
  ]);
  const hits: string[] = [];
  for (const file of sourceFiles(/\.ftl$/)) {
    readFileSync(file, 'utf8')
      .replace(/<#--[\s\S]*?-->/g, '')
      .split('\n')
      .forEach((line, index) => {
        if (/\?no_esc|<#noautoesc|kcSanitize/.test(line) && !allowed.has(line.trim())) hits.push(`${file.replace(themeRoot, '')}:${index + 1}: ${line.trim().slice(0, 90)}`);
      });
  }
  expect(hits).toEqual([]);
});

test('file and folder names in this folder are English', () => {
  // Project rule: new code names are English and ASCII (backend/AGENTS.md, section "Ad dili").
  // The list holds the Turkish words that were used as names here before.
  const turkish = /(^|[-_./])(akis|dil|eposta|erisilebilirlik|gorsel|hareket|odak|yerlesim|tema|deneme|referans|tunel|yatay|masaustu|giris|kayit|parola|hata|dogrulama|islem|kurulum|yolu)([-_./]|$)/;
  const names: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      if (entry === 'node_modules' || entry === '.env' || /^(test-results|playwright-report)/.test(entry)) continue;
      const path = join(dir, entry);
      names.push(path.slice(themeRoot.length));
      if (statSync(path).isDirectory()) walk(path);
    }
  };
  walk(themeRoot);
  expect(names.length).toBeGreaterThan(50);
  expect(names.filter((name) => !/^[\x20-\x7e]+$/.test(name)), 'names with non-ASCII letters').toEqual([]);
  expect(names.filter((name) => turkish.test(name)), 'Turkish names').toEqual([]);
});

test('templates do not use "javascript:" links', () => {
  // An action that sends a form is a button. A "javascript:" link also stops working under a strict content security policy.
  const hits: string[] = [];
  for (const file of sourceFiles(/\.ftl$/)) {
    readFileSync(file, 'utf8').split('\n').forEach((line, index) => {
      if (/href\s*=\s*["']\s*javascript:/i.test(line)) hits.push(`${file.replace(themeRoot, '')}:${index + 1}`);
    });
  }
  expect(hits).toEqual([]);
});

test('every "!important" in the styles has its reason written next to it', () => {
  // Project rule C-4: "!important" needs a reason. The reason is a comment that holds the word "important"
  // and sits inside the same rule or directly above it.
  const hits: string[] = [];
  for (const file of sourceFiles(/\.css$/)) {
    const lines = readFileSync(file, 'utf8').split('\n');
    lines.forEach((line, index) => {
      // A comment line that names "!important" is the reason itself, not a use.
      if (!line.includes('!important') || line.trim().startsWith('/*')) return;
      let start = index;
      while (start > 0 && !lines[start].includes('{')) start -= 1;
      while (start > 0 && !/^\s*$|\}\s*$/.test(lines[start - 1])) start -= 1;
      const block = lines.slice(start, index).join('\n');
      if (!/\/\*[^]*important[^]*\*\//i.test(block)) hits.push(`${file.replace(themeRoot, '')}:${index + 1}`);
    });
  }
  expect(hits).toEqual([]);
});

test('the shell script uses English names and messages', () => {
  const script = readFileSync(join(themeRoot, 'test', 'bin', 'theme-dev.sh'), 'utf8');
  expect(script).not.toMatch(/COLIMA_LIMA_AD/);
  const messages = script.split('\n').filter((line) => /^\s*echo\s+"/.test(line));
  expect(messages.length).toBeGreaterThan(3);
  expect(messages.filter((line) => /[çğıöşüÇĞİÖŞÜ]|Kullanım|Yalnız/.test(line))).toEqual([]);
  // A list of words is an array, not an unquoted expansion.
  expect(script).not.toMatch(/for \w+ in \$\{/);
});

test('the tests hold no fixed password or TOTP secret', () => {
  // Decision: the repository holds no fixed test secret. The values come from the environment.
  const helpers = readFileSync(join(themeRoot, 'test', 'tests', 'helpers.ts'), 'utf8');
  expect(helpers).toMatch(/PASSWORD = requiredSecret\('IDENTITY_TEST_PASSWORD'\)/);
  expect(helpers).toMatch(/TOTP_SECRET = requiredSecret\('IDENTITY_TEST_TOTP_SECRET'\)/);
  expect(helpers).not.toMatch(/(PASSWORD|SECRET)\s*=\s*['"`]/);
  const example = readFileSync(join(themeRoot, 'test', '.env.example'), 'utf8');
  expect(example).toMatch(/^IDENTITY_TEST_PASSWORD=$/m);
  expect(example).toMatch(/^IDENTITY_TEST_TOTP_SECRET=$/m);
});
