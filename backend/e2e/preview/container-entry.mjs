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
  await import('./run-tests.mjs');
} finally {
  for (const relay of relays) relay.close();
}
