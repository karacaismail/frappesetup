export function localUrl(host: string, offset: number): string {
  const port = Number(process.env.PANE_PORT);
  if (!Number.isInteger(port) || port < 1000 || port > 65526) {
    throw new Error('PANE_PORT must be an integer from 1000 to 65526.');
  }
  return `http://${host}:${port + offset}`;
}

export function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Missing test setting: ${name}`);
  return value;
}

export const account = 'e2e-user@example.test';
