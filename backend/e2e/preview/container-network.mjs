import { once } from 'node:events';
import { createConnection, createServer } from 'node:net';

// Both browser engines can treat *.localhost as loopback. Keep the original
// HTTP Host and OAuth origin while reaching the service over the preview network.
export async function forwardLoopback(localPort, service, servicePort) {
  const relay = createServer((client) => {
    const upstream = createConnection({ host: service, port: servicePort });
    upstream.on('error', () => client.destroy());
    client.on('error', () => upstream.destroy());
    client.pipe(upstream).pipe(client);
  });
  relay.listen(localPort, '127.0.0.1');
  await once(relay, 'listening');
  return relay;
}
