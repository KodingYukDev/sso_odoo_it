import assert from 'node:assert/strict';
import test from 'node:test';

import { OdooAccountsClient, OdooApiError } from '../src/odoo-client.js';

test('Odoo client sends server credential without exposing it in the body', async () => {
  let request;
  const client = new OdooAccountsClient({
    baseUrl: 'https://odoo.example.test/', apiKey: 'server-key',
    fetchImpl: async (url, options) => {
      request = { url, options };
      return new Response(JSON.stringify({ success: true, account: { sub: 'abc' } }), {
        status: 200, headers: { 'content-type': 'application/json' },
      });
    },
  });
  const result = await client.authenticate('student@example.test', 'not-logged');
  assert.equal(result.account.sub, 'abc');
  assert.equal(request.url, 'https://odoo.example.test/accounts/v1/authenticate');
  assert.equal(request.options.headers['X-Accounts-Key'], 'server-key');
  assert.equal(JSON.parse(request.options.body).identifier, 'student@example.test');
  assert.equal(request.options.body.includes('server-key'), false);
});

test('Odoo API errors remain typed and preserve public error code', async () => {
  const client = new OdooAccountsClient({
    baseUrl: 'https://odoo.example.test', apiKey: 'server-key',
    fetchImpl: async () => new Response(JSON.stringify({
      success: false, error: 'invalid_credentials', message: 'Invalid credentials.',
    }), { status: 401, headers: { 'content-type': 'application/json' } }),
  });
  await assert.rejects(() => client.authenticate('x', 'y'), (error) => {
    assert.ok(error instanceof OdooApiError);
    assert.equal(error.code, 'invalid_credentials');
    assert.equal(error.status, 401);
    return true;
  });
});
