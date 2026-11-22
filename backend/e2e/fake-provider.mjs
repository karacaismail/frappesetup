import { createServer } from 'node:http';

const base = Number(process.env.PANE_PORT);
if (!Number.isInteger(base) || base < 1000 || base > 65526) {
  throw new Error('PANE_PORT must be an integer from 1000 to 65526.');
}

const attempts = [];
const routes = new Map([['/limited/api/chat', 429], ['/fallback/api/chat', 200]]);
const responseBody = {
  model: 'e2e-local',
  message: { role: 'assistant', content: 'Local fallback response' },
  done: true,
  prompt_eval_count: 1,
  eval_count: 1,
};

createServer((request, response) => {
  response.setHeader('Content-Type', 'application/json');
  if (request.method === 'GET' && request.url === '/attempts') {
    response.end(JSON.stringify(attempts));
    return;
  }
  if (request.method === 'DELETE' && request.url === '/attempts') {
    attempts.length = 0;
    response.writeHead(204).end();
    return;
  }

  const status = routes.get(request.url);
  if (request.method !== 'POST' || !status) {
    response.writeHead(404).end();
    return;
  }

  request.resume();
  attempts.push(status);
  response.writeHead(status).end(JSON.stringify(
    status === 200 ? responseBody : { error: { message: 'Local test rate limit' } },
  ));
}).listen(base + 7, process.argv[2] ?? '127.0.0.1');
