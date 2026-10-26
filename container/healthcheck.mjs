import { containerAddress } from './address.mjs';
import { readFileSync } from 'node:fs';

try {
  const access = JSON.parse(readFileSync('/tmp/harness-access.json', 'utf8'));
  const token = new URL(access.url).searchParams.get('token');
  const origin = `http://${containerAddress()}:3080`;
  const exchange = await fetch(`${origin}/?token=${encodeURIComponent(token)}`, {
    redirect: 'manual', signal: AbortSignal.timeout(2000),
  });
  const cookies = exchange.headers.getSetCookie().map(value => value.split(';')[0]).join('; ');
  if (exchange.status !== 303 || !cookies) throw new Error(`Web authentication is not ready: HTTP ${exchange.status}`);
  const response = await fetch(`${origin}/`, {
    headers: { Cookie: cookies },
    signal: AbortSignal.timeout(4000),
  });
  const body = await response.text();
  if (!response.ok || !body.toLowerCase().includes('<html')) {
    throw new Error(`Web UI is not ready: HTTP ${response.status}`);
  }
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
