import { once } from 'node:events';
import { createServer } from 'node:http';
import { forwardLoopback } from './container-network.mjs';

const port = Number(process.env.PANE_PORT);
if (!/^[1-9][0-9]{3,4}$/.test(process.env.PANE_PORT ?? '') || port > 65526) {
  throw new Error('Invalid preview port.');
}

const relays = [];
try {
  for (const [offset, service, servicePort] of [
    [0, 'keycloak', port],
    [1, 'tenant-web', port + 1],
    [3, 'web', port + 3],
    [5, 'identity-sync', port + 5],
    [6, 'mailpit', 8025],
    [7, 'e2e-provider', port + 7],
  ]) {
    relays.push(await forwardLoopback(port + offset, service, servicePort));
  }
  if (process.env.E2E_FULL_BROWSER_FIXTURES === '1') {
    // Chromium and WebKit follow OAuth redirects directly. Serve the loopback
    // callback without storing or logging the query parameters.
    const callback = createServer((request, response) => {
      const path = request.url?.split('?', 1)[0];
      response.writeHead(path === '/callback' ? 200 : 404, { 'Cache-Control': 'no-store' });
      response.end();
    });
    callback.listen(port + 8, '127.0.0.1');
    await once(callback, 'listening');
    relays.push(callback);
  }
  await import('./run-tests.mjs');
} finally {
  for (const relay of relays) relay.close();
}
