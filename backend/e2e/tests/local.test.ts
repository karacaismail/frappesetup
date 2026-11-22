import assert from 'node:assert/strict';
import { test } from 'node:test';
import { localUrl } from '../local.ts';

test('the local origin accepts the same port format and bounds as the shell runner', (context) => {
  const previous = process.env.PANE_PORT;
  context.after(() => {
    if (previous === undefined) delete process.env.PANE_PORT;
    else process.env.PANE_PORT = previous;
  });

  for (const port of ['1e4', '0x1000', ' 43820 ', '04382', '65527']) {
    process.env.PANE_PORT = port;
    assert.throws(() => localUrl('kiraci1.localhost', 1), /PANE_PORT/, port);
  }
  process.env.PANE_PORT = '65526';
  assert.equal(localUrl('kiraci1.localhost', 1), 'http://kiraci1.localhost:65527');
});
