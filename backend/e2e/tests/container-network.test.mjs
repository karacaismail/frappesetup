import assert from 'node:assert/strict';
import { createServer, get } from 'node:http';
import { once } from 'node:events';
import { test } from 'node:test';

test('loopback relay preserves the browser origin and does not change the destination', async () => {
  const { forwardLoopback } = await import('../preview/container-network.mjs');
  const upstream = createServer((request, response) => response.end(request.headers.host));
  upstream.listen(0, '127.0.0.1');
  await once(upstream, 'listening');
  try {
    const relay = await forwardLoopback(0, '127.0.0.1', upstream.address().port);
    try {
      const body = await new Promise((resolve, reject) => {
        get({ host: '127.0.0.1', port: relay.address().port, headers: { Host: 'identity.localhost' } },
          (response) => {
            response.setEncoding('utf8');
            response.on('data', resolve);
            response.on('error', reject);
          }).on('error', reject);
      });
      assert.equal(body, 'identity.localhost');
      assert.equal(relay.address().address, '127.0.0.1');
    } finally {
      relay.close();
    }
  } finally {
    upstream.close();
  }
});
