import { createHmac } from 'node:crypto';

const PERIOD_MS = 30_000;
const BOUNDARY_GUARD_MS = 3_000;
const SETTLE_MS = 200;

function decodeBase32(secret: string): Buffer {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  const bits = secret.toUpperCase().replace(/=+$/, '').split('').map((letter) => {
    const index = alphabet.indexOf(letter);
    if (index < 0) throw new Error('The test OTP seed must be Base32.');
    return index.toString(2).padStart(5, '0');
  }).join('');
  return Buffer.from((bits.match(/.{8}/g) ?? []).map((byte) => Number.parseInt(byte, 2)));
}

export function totpCode(secret: string, atMs = Date.now()): string {
  const key = decodeBase32(secret);
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(atMs / PERIOD_MS)));
  const hash = createHmac('sha1', key).update(counter).digest();
  return String((hash.readUInt32BE(hash[hash.length - 1] & 15) & 0x7fffffff) % 1_000_000).padStart(6, '0');
}

export function invalidTotpCode(secret: string, atMs = Date.now()): string {
  const valid = new Set([
    totpCode(secret, atMs - PERIOD_MS),
    totpCode(secret, atMs),
    totpCode(secret, atMs + PERIOD_MS),
  ]);
  const wrong = ['000000', '111111', '222222', '333333'].find((candidate) => !valid.has(candidate));
  if (!wrong) throw new Error('Could not select an invalid TOTP code.');
  return wrong;
}

export function totpWaitMs(atMs: number, requireFreshPeriod: boolean): number {
  const elapsed = ((atMs % PERIOD_MS) + PERIOD_MS) % PERIOD_MS;
  const remaining = PERIOD_MS - elapsed;
  if (requireFreshPeriod || remaining < BOUNDARY_GUARD_MS) {
    return remaining + SETTLE_MS;
  }
  return 0;
}
