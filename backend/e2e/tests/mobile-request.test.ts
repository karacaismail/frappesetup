import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { test } from 'node:test';
import { postMobile } from '../mobile-request.ts';

test('phone requests send their installation ID without retaining session cookies', async (context) => {
  const headers: { installation?: string | string[]; cookie?: string }[] = [];
  const server = createServer((request, response) => {
    headers.push({ installation: request.headers['x-platform-installation'], cookie: request.headers.cookie });
    response.setHeader('Set-Cookie', 'sid=synthetic-session; Path=/');
    response.setHeader('Content-Type', 'application/json');
    response.end('{}');
  });
  await new Promise<void>((ready) => server.listen(0, '127.0.0.1', ready));
  context.after(() => server.close());
  const address = server.address();
  assert(address && typeof address !== 'string');
  const methods = 'http://127.0.0.1:' + address.port + '/api/method/';
  const installation = '98aeb05b-57aa-4b6d-9dfc-34da43ae7af4';

  await postMobile(methods, 'register', 'synthetic-token', installation);
  await postMobile(methods, 'revoke', 'synthetic-token', installation);
  await postMobile(methods, 'pull', 'synthetic-token', installation, {}, 'sid=synthetic-session');

  assert.deepEqual(headers, [
    { installation, cookie: undefined },
    { installation, cookie: undefined },
    { installation, cookie: 'sid=synthetic-session' },
  ]);
});
