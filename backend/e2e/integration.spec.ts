import { createHmac, randomUUID } from 'node:crypto';
import { expect, test, request as apiRequest, type APIRequestContext } from '@playwright/test';
import { localUrl, required } from './local';

function sessionHeaders(role: 'operator' | 'reader') {
  const prefix = `E2E_${role.toUpperCase()}`;
  return { Cookie: required(`${prefix}_COOKIE`), 'X-Frappe-CSRF-Token': required(`${prefix}_CSRF`) };
}

const aiMethod = (method: string) =>
  `${localUrl('kiraci1.localhost', 1)}/api/method/platform_core.api.ai.${method}`;

async function issueAgentToken(request: APIRequestContext, role: 'operator' | 'reader') {
  const response = await request.post(aiMethod('issue_agent_token'), {
    headers: sessionHeaders(role), maxRedirects: 0,
  });
  expect(response.status()).toBe(200);
  const { token } = (await response.json()).message;
  expect(typeof token).toBe('string');
  return token as string;
}

function bearer(token: string) {
  return { Authorization: `Bearer ${token}` };
}

function mcpCall(name: string, args: object) {
  return { jsonrpc: '2.0', id: randomUUID(), method: 'tools/call', params: { name, arguments: args } };
}

async function withFreshRequest<T>(run: (request: APIRequestContext) => Promise<T>): Promise<T> {
  const request = await apiRequest.newContext();
  try {
    return await run(request);
  } finally {
    await request.dispose();
  }
}

async function mcp(token: string, name: string, args: object) {
  return withFreshRequest(async (request) => {
    const data = mcpCall(name, args);
    const response = await request.post(aiMethod('mcp'), {
      maxRedirects: 0,
      headers: { ...bearer(token), 'Mcp-Conversation-Id': randomUUID() },
      data,
    });
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.jsonrpc).toBe('2.0');
    expect(body.id).toBe(data.id);
    expect(body.error).toBeUndefined();
    return body.result;
  });
}

function fixtures() {
  return {
    doctype: required('E2E_DOCTYPE'),
    visible: required('E2E_VISIBLE_RECORD'),
    hidden: required('E2E_HIDDEN_RECORD'),
  };
}

async function resource(request: APIRequestContext, doctype: string, name?: string, role: 'operator' | 'reader' = 'reader', params?: Record<string, string | number>) {
  const path = [doctype, ...(name ? [name] : [])].map(encodeURIComponent).join('/');
  return request.get(`${localUrl('kiraci1.localhost', 1)}/api/resource/${path}`, {
    headers: sessionHeaders(role),
    params,
    maxRedirects: 0,
  });
}

test('identity sync provisions a Website User', async ({ request }) => {
  const syncAccount = required('E2E_SYNC_EMAIL');
  if (!/^e2e-sync(?:-[a-z0-9-]+)?@example\.test$/.test(syncAccount)) {
    throw new Error('E2E_SYNC_EMAIL must be a synthetic identity sync account.');
  }
  const before = await resource(request, 'User', syncAccount, 'operator');
  expect(before.status()).toBe(404);
  const now = Date.now();
  const timestamp = Math.floor(now / 1000);
  const data = JSON.stringify({
    id: randomUUID(), kind: 'user', type: 'VERIFY_EMAIL', realm: 'platform',
    time: now, user_id: required('E2E_SYNC_SUBJECT'),
  });
  const signature = createHmac('sha256', required('IDENTITY_SYNC_WEBHOOK_SECRET'))
    .update(`${timestamp}.execute.${data}`).digest('hex');
  const response = await request.post(`${localUrl('127.0.0.1', 5)}/v1/events`, {
    maxRedirects: 0,
    headers: {
      'Content-Type': 'application/json',
      'X-Identity-Sync-Timestamp': String(timestamp),
      'X-Identity-Sync-Signature': `sha256=${signature}`,
    },
    data,
  });
  expect(response.ok()).toBe(true);
  expect((await response.json()).status).toBe('processed');
  const user = await resource(request, 'User', syncAccount, 'operator');
  expect(user.status()).toBe(200);
  expect((await user.json()).data.user_type).toBe('Website User');
});

test('agent token lists permitted records only', async ({ request }) => {
  const { doctype, visible, hidden } = fixtures();
  const token = await issueAgentToken(request, 'reader');
  const result = await mcp(token, 'list_documents', {
    doctype, filters: { name: ['in', [visible, hidden]] }, fields: ['name'],
  });
  expect(result.isError).toBe(false);
  expect(result.structuredContent.documents).toEqual([{ name: visible }]);
  const denied = await mcp(token, 'get_document', { doctype, name: hidden });
  expect(denied.isError).toBe(true);
  expect(denied.structuredContent?.error?.code).toBe('permission');
});

test('MCP rejects an agent token sent with a session cookie', async ({ request }) => {
  const token = await issueAgentToken(request, 'reader');
  const response = await request.post(aiMethod('mcp'), {
    headers: { ...sessionHeaders('reader'), ...bearer(token), 'Mcp-Conversation-Id': randomUUID() },
    data: mcpCall('list_documents', { doctype: fixtures().doctype }),
    maxRedirects: 0,
  });
  expect(response.status()).toBe(403);
});

test('an update takes effect only after one valid human approval', async ({ request }) => {
  const { doctype, visible: name } = fixtures();
  const field = required('E2E_UPDATE_FIELD');
  const value = `Integration ${randomUUID()}`;
  const headers = sessionHeaders('operator');
  const readValue = async () => {
    const record = await resource(request, doctype, name, 'operator');
    expect(record.status()).toBe(200);
    return (await record.json()).data[field];
  };
  const before = await readValue();
  expect(before).toBeDefined();
  const token = await issueAgentToken(request, 'operator');
  const result = await mcp(token, 'update_document', { doctype, name, data: { [field]: value } });
  expect(result.isError).toBe(false);
  expect(result.structuredContent.status).toBe('approval_required');
  const { proposal_id } = result.structuredContent;
  expect(await readValue()).toBe(before);

  const listing = await request.get(aiMethod('list_proposals'), {
    headers, params: { limit: 1 }, maxRedirects: 0,
  });
  expect(listing.status()).toBe(200);
  const { proposals, has_next_page: hasNextPage } = (await listing.json()).message;
  expect(proposals).toHaveLength(1);
  expect(proposals[0]).toMatchObject({ proposal_id, status: 'pending' });
  expect(typeof hasNextPage).toBe('boolean');

  const preview = await request.get(aiMethod('get_proposal'), { headers, params: { proposal_id }, maxRedirects: 0 });
  expect(preview.status()).toBe(200);
  const { digest } = (await preview.json()).message;
  expect(digest).toMatch(/^[a-f0-9]{64}$/);

  await withFreshRequest(async (agent) => {
    const denied = await agent.post(aiMethod('approve_proposal'), {
      headers: bearer(token), data: { proposal_id, digest }, maxRedirects: 0,
    });
    expect(denied.status()).toBe(401);
  });
  expect(await readValue()).toBe(before);

  const approve = async (approvalDigest: string) => {
    const response = await request.post(aiMethod('approve_proposal'), {
      headers, data: { proposal_id, digest: approvalDigest }, maxRedirects: 0,
    });
    expect(response.status()).toBe(200);
    return (await response.json()).message;
  };
  const wrongDigest = (digest[0] === '0' ? '1' : '0') + digest.slice(1);
  expect(await approve(wrongDigest)).toMatchObject({ executed: false, deny_reason: 'digest_mismatch' });
  expect(await readValue()).toBe(before);

  expect(await approve(digest)).toMatchObject({ executed: true });
  expect(await readValue()).toBe(value);
  expect(await approve(digest)).toMatchObject({ executed: false, deny_reason: 'not_pending' });
  expect(await readValue()).toBe(value);
});

test('model gateway falls back after the first provider returns 429', async ({ request }) => {
  const attemptsUrl = `${localUrl('127.0.0.1', 7)}/attempts`;
  const reset = await request.delete(attemptsUrl, { maxRedirects: 0 });
  expect(reset.status()).toBe(204);
  const response = await request.post(
    `${localUrl('kiraci1.localhost', 1)}/api/method/platform_core.api.model.complete`,
    { headers: sessionHeaders('operator'), maxRedirects: 0,
      data: { route: required('E2E_MODEL_ROUTE'), messages: [{ role: 'user', content: 'Integration test' }] } },
  );
  expect(response.status()).toBe(200);
  const result = (await response.json()).message;
  expect(result.api).toBe(required('E2E_FALLBACK_API'));
  expect(result.text).toBe('Local fallback response');
  const evidence = await request.get(attemptsUrl, { maxRedirects: 0 });
  expect(evidence.status()).toBe(200);
  expect(await evidence.json()).toEqual([429, 200]);
});

test('access rule applies equally to list and detail', async ({ request }) => {
  const { doctype, visible, hidden } = fixtures();
  const summary = await request.get(
    `${localUrl('kiraci1.localhost', 1)}/api/method/platform_core.api.access.get_access_summary`,
    { headers: sessionHeaders('reader'), params: { doctype }, maxRedirects: 0 },
  );
  expect(summary.status()).toBe(200);
  expect((await summary.json()).message).toMatchObject({ doctype, governed: true });
  const params = {
    filters: JSON.stringify([['name', 'in', [visible, hidden]]]),
    limit_page_length: 0,
  };
  const baseline = await resource(request, doctype, undefined, 'operator', params);
  expect(baseline.status()).toBe(200);
  const baselineNames = (await baseline.json()).data.map((record: { name: string }) => record.name);
  expect(baselineNames.sort()).toEqual([visible, hidden].sort());
  const list = await resource(request, doctype, undefined, 'reader', params);
  expect(list.status()).toBe(200);
  const names = (await list.json()).data.map((record: { name: string }) => record.name);
  expect(names).toContain(visible);
  expect(names).not.toContain(hidden);
  expect((await resource(request, doctype, visible)).status()).toBe(200);
  expect((await resource(request, doctype, hidden)).status()).toBe(403);
});
