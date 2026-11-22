import { once } from 'node:events';
import { createServer as createHttpServer } from 'node:http';
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

export async function listenOAuthCallback(port) {
  const callback = createHttpServer((request, response) => {
    const path = request.url?.split('?', 1)[0];
    response.writeHead(request.method === 'GET' && path === '/callback' ? 200 : 404,
      { 'Cache-Control': 'no-store' });
    response.end();
  });
  callback.listen(port, '127.0.0.1');
  await once(callback, 'listening');
  return callback;
}
