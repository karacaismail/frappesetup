import { createHmac, randomUUID } from 'node:crypto';
import { expect, test, type APIRequestContext } from '@playwright/test';
import { localUrl, required, syncAccount } from './local';

function sessionHeaders(role: 'operator' | 'reader') {
  const prefix = `E2E_${role.toUpperCase()}`;
  return { Cookie: required(`${prefix}_COOKIE`), 'X-Frappe-CSRF-Token': required(`${prefix}_CSRF`) };
}

async function mcp(request: APIRequestContext, token: string, name: string, args: object) {
  const id = randomUUID();
  const response = await request.post(`${localUrl('kiraci1.localhost', 1)}/api/method/platform_core.api.ai.mcp`, {
    maxRedirects: 0,
    headers: { Authorization: `Bearer ${token}`, 'Mcp-Conversation-Id': randomUUID() },
    data: { jsonrpc: '2.0', id, method: 'tools/call', params: { name, arguments: args } },
  });
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body.jsonrpc).toBe('2.0');
  expect(body.id).toBe(id);
  expect(body.error).toBeUndefined();
  return body.result;
}

function fixtures() {
  return {
    doctype: required('E2E_DOCTYPE'),
    visible: required('E2E_VISIBLE_RECORD'),
    hidden: required('E2E_HIDDEN_RECORD'),
  };
}

async function resource(request: APIRequestContext, doctype: string, name?: string, role: 'operator' | 'reader' = 'reader') {
  const path = [doctype, ...(name ? [name] : [])].map(encodeURIComponent).join('/');
  return request.get(`${localUrl('kiraci1.localhost', 1)}/api/resource/${path}`, {
    headers: sessionHeaders(role),
    maxRedirects: 0,
  });
}

test('identity sync provisions a Website User', async ({ request }) => {
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
  const user = await resource(request, 'User', syncAccount, 'operator');
  expect(user.status()).toBe(200);
  expect((await user.json()).data.user_type).toBe('Website User');
});

test('agent token lists permitted records only', async ({ request }) => {
  const { doctype, visible, hidden } = fixtures();
  const response = await request.post(
    `${localUrl('kiraci1.localhost', 1)}/api/method/platform_core.api.ai.issue_agent_token`,
    { headers: sessionHeaders('reader'), maxRedirects: 0 },
  );
  expect(response.status()).toBe(200);
  const { token } = (await response.json()).message;
  const result = await mcp(request, token, 'list_documents', {
    doctype, filters: { name: ['in', [visible, hidden]] }, fields: ['name'],
  });
  expect(result.isError).toBe(false);
  expect(result.structuredContent.documents).toEqual([{ name: visible }]);
  const denied = await mcp(request, token, 'get_document', { doctype, name: hidden });
  expect(denied.isError).toBe(true);
});

test('an update takes effect only after human approval', async ({ request }) => {
  const { doctype, visible: name } = fixtures();
  const field = required('E2E_UPDATE_FIELD');
  const value = `Integration ${randomUUID()}`;
  const base = `${localUrl('kiraci1.localhost', 1)}/api/method/platform_core.api.ai.`;
  const headers = sessionHeaders('operator');
  const readValue = async () => {
    const record = await resource(request, doctype, name, 'operator');
    expect(record.status()).toBe(200);
    return (await record.json()).data[field];
  };
  const before = await readValue();
  expect(before).toBeDefined();
  const rpc = await request.post(`${base}mcp`, {
    headers: { ...headers, 'Mcp-Conversation-Id': randomUUID() },
    maxRedirects: 0,
    data: { jsonrpc: '2.0', id: 1, method: 'tools/call',
      params: { name: 'update_document', arguments: { doctype, name, data: { [field]: value } } } },
  });
  expect(rpc.status()).toBe(200);
  const { result } = await rpc.json();
  expect(result.isError).toBe(false);
  const { proposal_id } = result.structuredContent;
  expect(await readValue()).toBe(before);

  const preview = await request.get(`${base}get_proposal`, { headers, params: { proposal_id }, maxRedirects: 0 });
  expect(preview.status()).toBe(200);
  const { digest } = (await preview.json()).message;
  const approved = await request.post(`${base}approve_proposal`, {
    headers, data: { proposal_id, digest }, maxRedirects: 0,
  });
  expect(approved.status()).toBe(200);
  expect(await readValue()).toBe(value);
});

test('model gateway falls back after the first provider returns 429', async ({ request }) => {
  const attemptsUrl = `${localUrl('127.0.0.1', 7)}/attempts`;
  const reset = await request.delete(attemptsUrl, { maxRedirects: 0 });
  expect(reset.status()).toBe(204);
  const response = await request.post(
    `${localUrl('kiraci1.localhost', 1)}/api/method/platform_core.api.model.complete`,
    { headers: sessionHeaders('operator'), maxRedirects: 0,
      data: { route: 'e2e-local-only', messages: [{ role: 'user', content: 'Integration test' }] } },
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
  const list = await resource(request, doctype);
  expect(list.status()).toBe(200);
  const names = (await list.json()).data.map((record: { name: string }) => record.name);
  expect(names).toContain(visible);
  expect(names).not.toContain(hidden);
  expect((await resource(request, doctype, visible)).status()).toBe(200);
  expect([403, 404]).toContain((await resource(request, doctype, hidden)).status());
});
