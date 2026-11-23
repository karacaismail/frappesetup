import { randomUUID } from 'node:crypto';
import { request as httpRequest } from 'node:http';

const ALLOWED_HOSTS = new Set(['127.0.0.1', 'localhost', 'identity.localhost']);

type SyncUserOptions = {
  identityOrigin: string;
  syncOrigin: string;
  clientId: string;
  clientSecret: string;
  organizationAlias?: string;
  settleMs?: number;
};

type RawReply = {
  status: number;
  location?: string;
  body: string;
};

function assertLocalOrigin(origin: string): URL {
  const parsed = new URL(origin);
  if (parsed.protocol !== 'http:' || !ALLOWED_HOSTS.has(parsed.hostname) || parsed.username || parsed.password) {
    throw new Error('Sync fixture requests must target a local HTTP origin without credentials.');
  }
  return parsed;
}

function sendLocal(origin: string, path: string, options: {
  method?: string;
  headers?: Record<string, string>;
  body?: string;
} = {}): Promise<RawReply> {
  const base = assertLocalOrigin(origin);
  const connectHost = base.hostname.endsWith('.localhost') ? '127.0.0.1' : base.hostname;
  return new Promise((resolve, reject) => {
    const req = httpRequest({
      host: connectHost,
      port: Number(base.port || 80),
      path,
      method: options.method ?? 'GET',
      headers: {
        Host: base.host,
        ...(options.body !== undefined ? { 'Content-Length': String(Buffer.byteLength(options.body)) } : {}),
        ...(options.headers ?? {}),
      },
      timeout: 15_000,
    }, (res) => {
      const chunks: Buffer[] = [];
      res.on('data', (chunk) => chunks.push(chunk));
      res.on('end', () => resolve({
        status: res.statusCode ?? 0,
        location: typeof res.headers.location === 'string' ? res.headers.location : undefined,
        body: Buffer.concat(chunks).toString('utf8'),
      }));
    });
    req.on('timeout', () => req.destroy(new Error('Sync fixture HTTP request timed out.')));
    req.on('error', reject);
    if (options.body !== undefined) req.write(options.body);
    req.end();
  });
}

export async function provisionUnlinkedSyncUser({
  identityOrigin,
  syncOrigin,
  clientId,
  clientSecret,
  organizationAlias = 'tenant1',
  settleMs = 350,
}: SyncUserOptions): Promise<{ email: string; subject: string }> {
  const tokenForm = new URLSearchParams({
    grant_type: 'client_credentials',
    client_id: clientId,
    client_secret: clientSecret,
    scope: 'admin-api kc-admin-api',
  }).toString();
  const tokenReply = await sendLocal(identityOrigin, '/realms/platform/protocol/openid-connect/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: tokenForm,
  });
  if (tokenReply.status !== 200) {
    throw new Error(`Sync fixture token request returned HTTP ${tokenReply.status}.`);
  }
  const { access_token: token } = JSON.parse(tokenReply.body) as { access_token?: string };
  if (!token) throw new Error('Sync fixture token is missing.');

  const authHeaders = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
  const email = `e2e-sync-${randomUUID()}@example.test`;
  const created = await sendLocal(identityOrigin, '/admin/realms/platform/users', {
    method: 'POST',
    headers: authHeaders,
    body: JSON.stringify({
      username: email,
      email,
      emailVerified: true,
      enabled: true,
      firstName: 'Integration',
      lastName: 'Sync',
    }),
  });
  if (created.status !== 201 || !created.location) {
    throw new Error(`Sync fixture user creation returned HTTP ${created.status}.`);
  }
  const subject = decodeURIComponent(created.location.replace(/\/+$/, '').split('/').pop() ?? '');
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(subject)) {
    throw new Error('Sync fixture returned an invalid user identifier.');
  }

  // Drain any async USER_CREATE webhook while the account has no organization memberships.
  await new Promise((resolve) => setTimeout(resolve, settleMs));
  const health = await sendLocal(syncOrigin, '/healthz');
  if (health.status !== 200) {
    throw new Error(`Identity sync health check returned HTTP ${health.status}.`);
  }

  const orgQuery = new URLSearchParams({ search: organizationAlias }).toString();
  const orgReply = await sendLocal(identityOrigin, `/admin/realms/platform/organizations?${orgQuery}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (orgReply.status !== 200) {
    throw new Error(`Sync fixture organization lookup returned HTTP ${orgReply.status}.`);
  }
  const organizations = JSON.parse(orgReply.body) as { id?: string; alias?: string }[];
  const organization = organizations.find((entry) => entry.alias === organizationAlias);
  if (!organization?.id) {
    throw new Error(`Sync fixture could not find Keycloak organization ${organizationAlias}.`);
  }

  const memberReply = await sendLocal(
    identityOrigin,
    `/admin/realms/platform/organizations/${encodeURIComponent(organization.id)}/members`,
    {
      method: 'POST',
      headers: authHeaders,
      body: JSON.stringify(subject),
    },
  );
  if (![201, 204].includes(memberReply.status)) {
    throw new Error(`Sync fixture organization membership returned HTTP ${memberReply.status}.`);
  }

  return { email, subject };
}
