import assert from 'node:assert/strict';
import test from 'node:test';

import { loadConfig } from '../src/config.js';

test('development configuration has safe parsed defaults', () => {
  const config = loadConfig({});
  assert.equal(config.publicOrigin, 'http://localhost:3000');
  assert.deepEqual(config.fallbackClients, []);
  assert.equal(config.NODE_ENV, 'development');
});

test('production requires persistent Redis and signing keys', () => {
  assert.throws(() => loadConfig({
    NODE_ENV: 'production',
    PUBLIC_ORIGIN: 'https://accounts.kodingyuk.id',
    ODOO_ACCOUNTS_API_KEY: 'secret',
    COOKIE_KEYS: `${'a'.repeat(32)},${'b'.repeat(32)}`,
  }), /REDIS_URL/);
});
