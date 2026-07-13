import assert from 'node:assert/strict';
import { createHash, randomBytes } from 'node:crypto';
import { once } from 'node:events';
import test from 'node:test';

import { createApp } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { createProvider } from '../src/provider.js';

function base64url(value) { return value.toString('base64url'); }

test('authorization code + PKCE completes without exposing an Odoo session', async (t) => {
  const port = 32000 + Math.floor(Math.random() * 1000);
  const origin = `http://localhost:${port}`;
  const callback = 'http://localhost:4000/callback';
  const account = {
    sub: '0ed352c9-589b-4f67-80dd-d804ff599eca', name: 'Siswa Demo',
    preferred_username: 'siswa.demo', email: 'siswa@example.test',
    email_verified: false, account_type: 'public', is_student: false,
    locale: 'id_ID', zoneinfo: 'Asia/Jakarta',
  };
  const audits = [];
  const odoo = {
    clients: async () => [{
      client_id: 'integration-test', client_name: 'Integration Test',
      redirect_uris: [callback], response_types: ['code'],
      grant_types: ['authorization_code'], token_endpoint_auth_method: 'none',
    }],
    authenticate: async () => ({ account }),
    claims: async () => ({ account }),
    claimStudent: async () => ({ claim: { status: 'pending' } }),
    audit: async (entry) => { audits.push(entry); },
  };
  const config = loadConfig({
    NODE_ENV: 'test', PORT: String(port), PUBLIC_ORIGIN: origin,
    ODOO_BASE_URL: 'http://odoo.test', ODOO_ACCOUNTS_API_KEY: 'test-key',
    COOKIE_KEYS: 'test-cookie-key-one,test-cookie-key-two', OIDC_CLIENTS_JSON: '[]',
  });
  const logger = { warn() {}, error() {}, log() {} };
  const provider = await createProvider({ config, odoo, logger });
  const app = createApp({ config, odoo, provider, logger });
  const server = app.listen(port);
  await once(server, 'listening');
  t.after(() => server.close());

  const cookies = new Map();
  async function request(url, options = {}) {
    const cookie = [...cookies].map(([name, value]) => `${name}=${value}`).join('; ');
    const response = await fetch(new URL(url, origin), {
      redirect: 'manual', ...options,
      headers: { ...(cookie ? { Cookie: cookie } : {}), ...(options.headers || {}) },
    });
    for (const header of response.headers.getSetCookie()) {
      const [pair] = header.split(';');
      const index = pair.indexOf('=');
      cookies.set(pair.slice(0, index), pair.slice(index + 1));
    }
    return response;
  }

  const verifier = base64url(randomBytes(48));
  const challenge = base64url(createHash('sha256').update(verifier).digest());
  const authorize = new URL('/oauth/authorize', origin);
  authorize.search = new URLSearchParams({
    client_id: 'integration-test', redirect_uri: callback, response_type: 'code',
    scope: 'openid profile email student.basic', state: 'fixed-state', nonce: 'fixed-nonce',
    code_challenge: challenge, code_challenge_method: 'S256',
  });

  let response = await request(authorize);
  assert.ok([302, 303].includes(response.status));
  let location = response.headers.get('location');
  assert.match(location, /^\/interaction\//);

  response = await request(location);
  assert.equal(response.status, 200);
  assert.match(await response.text(), /Selamat datang kembali/);

  response = await request(`${location}/login`, {
    method: 'POST',
    headers: { Origin: origin, 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ identifier: 'siswa@example.test', password: 'valid-password' }),
  });
  assert.equal(response.status, 303);
  location = response.headers.get('location');

  response = await request(location);
  assert.ok([302, 303].includes(response.status));
  location = response.headers.get('location');
  assert.match(location, /^\/interaction\//);

  response = await request(location);
  assert.equal(response.status, 200);
  assert.match(await response.text(), /Persetujuan akses/);

  response = await request(`${location}/confirm`, {
    method: 'POST', headers: { Origin: origin, 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  assert.equal(response.status, 303);
  location = response.headers.get('location');

  response = await request(location);
  assert.ok([302, 303].includes(response.status));
  const callbackUrl = new URL(response.headers.get('location'));
  assert.equal(callbackUrl.origin + callbackUrl.pathname, callback);
  assert.equal(callbackUrl.searchParams.get('state'), 'fixed-state');
  const code = callbackUrl.searchParams.get('code');
  assert.ok(code);

  response = await request('/oauth/token', {
    method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'authorization_code', client_id: 'integration-test', code,
      redirect_uri: callback, code_verifier: verifier,
    }),
  });
  assert.equal(response.status, 200);
  const tokens = await response.json();
  assert.equal(tokens.token_type, 'Bearer');
  assert.ok(tokens.access_token);
  assert.ok(tokens.id_token);
  assert.equal('session_id' in tokens, false);
  assert.ok(audits.some((entry) => entry.event === 'oidc.authorization_succeeded'));
  assert.ok(audits.some((entry) => entry.event === 'oidc.token_issued'));
});
