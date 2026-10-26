import { spawn } from 'node:child_process';
import { writeFileSync, rmSync } from 'node:fs';
import { createInterface } from 'node:readline';
import { containerAddress } from './address.mjs';

const publicUrl = new URL(process.env.HARNESS_PUBLIC_URL ?? 'http://127.0.0.1:3080');
if (publicUrl.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(publicUrl.hostname)) {
  throw new Error('This local deployment requires a loopback HTTP public URL. Use an SSH tunnel for server access.');
}
const child = spawn('/opt/harness/node_modules/.bin/dsh', [
  'web', '--patch', '/opt/harness/container/local.patch.yml',
  '--no-open', '--host', containerAddress(), '--port', '3080',
  '--public-url', publicUrl.origin,
  '--trusted-host', publicUrl.host,
  '--trusted-host', `localhost:${publicUrl.port || '80'}`,
], { stdio: ['inherit', 'pipe', 'pipe'] });

rmSync('/tmp/harness-access.json', { force: true });
for (const stream of [child.stdout, child.stderr]) {
  createInterface({ input: stream }).on('line', line => {
    const match = line.match(/dsh web: (http:\/\/\S+\?token=\S+)/);
    if (match) {
      const url = new URL(match[1]);
      if (url.origin === publicUrl.origin && url.searchParams.has('token')) {
        writeFileSync('/tmp/harness-access.json', JSON.stringify({ url: url.href }), { mode: 0o600 });
      }
    }
    console.log(line.replace(/([?&]token=)[^\s&]+/g, '$1[redacted]'));
  });
}

for (const signal of ['SIGTERM', 'SIGINT']) {
  process.on(signal, () => child.kill(signal));
}
child.on('error', error => {
  console.error(`Harness launch failed: ${error.message}`);
  process.exitCode = 1;
});
child.on('exit', (code, signal) => {
  process.exitCode = code ?? (signal === 'SIGTERM' || signal === 'SIGINT' ? 0 : 1);
});
