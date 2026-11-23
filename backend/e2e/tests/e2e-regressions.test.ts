import assert from 'node:assert/strict';
import { createHmac } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { invalidTotpCode, totpCode, totpWaitMs } from '../totp.ts';
import { provisionUnlinkedSyncUser } from '../sync-fixture.ts';

function encodeBase32(input: Buffer): string {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  let bits = '';
  for (const byte of input) bits += byte.toString(2).padStart(8, '0');
  let output = '';
  for (let index = 0; index < bits.length; index += 5) {
    output += alphabet[Number.parseInt(bits.slice(index, index + 5).padEnd(5, '0'), 2)];
  }
  return output;
}

test('totpCode matches Keycloak raw UTF-8 secret bytes encoded as Base32', () => {
  const rawKeycloakValue = 'sample-keycloak-otp-value-0123';
  const seed = encodeBase32(Buffer.from(rawKeycloakValue, 'utf8'));
  const atMs = 59_000;
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(1n);
  const digest = createHmac('sha1', Buffer.from(rawKeycloakValue, 'utf8')).update(counter).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  const expected = String((digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, '0');

  assert.equal(totpCode(seed, atMs), expected);
  assert.throws(() => totpCode('not-base32!'), /Base32/);
});

test('invalidTotpCode never collides with adjacent TOTP windows', () => {
  const seed = encodeBase32(Buffer.from('12345678901234567890', 'utf8'));
  const atMs = 90_000;
  const adjacent = new Set([
    totpCode(seed, atMs - 30_000),
    totpCode(seed, atMs),
    totpCode(seed, atMs + 30_000),
  ]);
  const wrong = invalidTotpCode(seed, atMs);
  assert.match(wrong, /^[0-9]{6}$/);
  assert.equal(adjacent.has(wrong), false);
});

test('totpWaitMs avoids period-end expiry and shared-account code reuse', () => {
  assert.equal(totpWaitMs(5_000, false), 0);
  const nearEnd = totpWaitMs(28_500, false);
  assert.ok(nearEnd >= 1_500 && nearEnd <= 2_000, `expected boundary wait, got ${nearEnd}`);
  const nextWindow = totpWaitMs(12_000, true);
  assert.ok(nextWindow >= 18_000 && nextWindow <= 18_500, `expected fresh window wait, got ${nextWindow}`);
});

test('provisionUnlinkedSyncUser creates a unique user per run and drains healthz before org membership', async (context) => {
  const events: string[] = [];
  let userCounter = 0;
  const server = createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on('data', (chunk) => chunks.push(chunk));
    req.on('end', () => {
      const body = Buffer.concat(chunks).toString('utf8');
      if (req.method === 'POST' && req.url === '/realms/platform/protocol/openid-connect/token') {
        events.push('token:' + body);
        res.setHeader('Content-Type', 'application/json');
        res.end(JSON.stringify({ access_token: 'synthetic-kc-admin-access' }));
        return;
      }
      if (req.method === 'POST' && req.url === '/admin/realms/platform/users') {
        userCounter += 1;
        const parsed = JSON.parse(body);
        events.push(`create_user:${parsed.email}:${parsed.emailVerified}`);
        res.statusCode = 201;
        res.setHeader('Location', `http://127.0.0.1/admin/realms/platform/users/sub-${userCounter}`);
        res.end();
        return;
      }
      if (req.method === 'GET' && req.url === '/healthz') {
        events.push('sync_healthz');
        res.statusCode = 200;
        res.end('ok');
        return;
      }
      if (req.method === 'GET' && req.url?.startsWith('/admin/realms/platform/organizations?')) {
        const query = new URL(req.url, 'http://127.0.0.1').searchParams;
        events.push('list_orgs:' + query.toString());
        res.setHeader('Content-Type', 'application/json');
        // Keycloak's search matches name and domain, never alias: a search for the alias finds nothing.
        if (query.has('search')) { res.end('[]'); return; }
        const page = Number(query.get('first')) === 0
          ? [{ id: 'org-other', alias: 'other', name: 'Other' }, { id: 'org-tenant1', alias: 'tenant1', name: 'Preview Integration Tenant' }]
          : [];
        res.end(JSON.stringify(page));
        return;
      }
      if (req.method === 'POST' && req.url === '/admin/realms/platform/organizations/org-tenant1/members') {
        events.push('add_member:' + JSON.parse(body));
        res.statusCode = 204;
        res.end();
        return;
      }
      res.statusCode = 404;
      res.end();
    });
  });
  await new Promise<void>((ready) => server.listen(0, '127.0.0.1', ready));
  context.after(() => server.close());
  const address = server.address();
  assert(address && typeof address !== 'string');
  const origin = `http://127.0.0.1:${address.port}`;

  const first = await provisionUnlinkedSyncUser({
    identityOrigin: origin,
    syncOrigin: origin,
    clientId: 'e2e-sync-fixture',
    clientSecret: 'synthetic-client-value',
    settleMs: 1,
  });
  const second = await provisionUnlinkedSyncUser({
    identityOrigin: origin,
    syncOrigin: origin,
    clientId: 'e2e-sync-fixture',
    clientSecret: 'synthetic-client-value',
    settleMs: 1,
  });

  assert.match(first.email, /^e2e-sync-[0-9a-f-]+@example\.test$/);
  assert.match(second.email, /^e2e-sync-[0-9a-f-]+@example\.test$/);
  assert.notEqual(first.email, second.email);
  assert.equal(first.subject, 'sub-1');
  assert.equal(second.subject, 'sub-2');

  assert.ok(events.some((item) => item.startsWith('list_orgs:') && item.includes('first=0') && !item.includes('search=')), JSON.stringify(events));
  const createIndex = events.findIndex((item) => item.startsWith('create_user:'));
  const healthIndex = events.indexOf('sync_healthz');
  const memberIndex = events.indexOf('add_member:sub-1');
  assert.ok(createIndex >= 0 && createIndex < healthIndex && healthIndex < memberIndex, JSON.stringify(events));
});

test('mobile-pkce spec mints the wrong-audience token immediately before use and integration spec avoids static sync env', () => {
  const mobileSpec = readFileSync(fileURLToPath(new URL('../mobile-pkce.spec.ts', import.meta.url)), 'utf8');
  assert.equal(mobileSpec.includes('E2E_MOBILE_WRONG_AUDIENCE_TOKEN'), false);
  const expiredIndex = mobileSpec.indexOf('const expiredClaims = claims(expired)');
  const wrongMintIndex = mobileSpec.indexOf("'openid mobile'");
  const wrongClaimsIndex = mobileSpec.indexOf('const wrongClaims = claims(wrong)');
  assert.ok(expiredIndex > 0 && expiredIndex < wrongMintIndex && wrongMintIndex < wrongClaimsIndex);

  const integrationSpec = readFileSync(fileURLToPath(new URL('../integration.spec.ts', import.meta.url)), 'utf8');
  assert.equal(integrationSpec.includes('E2E_SYNC_EMAIL'), false);
  assert.equal(integrationSpec.includes('E2E_SYNC_SUBJECT'), false);
  assert.ok(integrationSpec.includes('provisionUnlinkedSyncUser'));
});
