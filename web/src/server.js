import Redis from 'ioredis';

import { createApp } from './app.js';
import { loadConfig } from './config.js';
import { OdooAccountsClient } from './odoo-client.js';
import { createProvider } from './provider.js';
import { createRedisAdapter } from './redis-adapter.js';

const config = loadConfig();
const odoo = new OdooAccountsClient({
  baseUrl: config.odooBaseUrl,
  apiKey: config.ODOO_ACCOUNTS_API_KEY,
});

let redis;
let adapter;
if (config.REDIS_URL) {
  redis = new Redis(config.REDIS_URL, { lazyConnect: true, maxRetriesPerRequest: 2 });
  await redis.connect();
  await redis.ping();
  adapter = createRedisAdapter(redis);
} else {
  console.warn('REDIS_URL is not set; using in-memory OIDC state for development only.');
}

const provider = await createProvider({ config, odoo, adapter });
const app = createApp({ config, odoo, provider });
const server = app.listen(config.PORT, () => {
  console.log(`KodingYuk Account listening at ${config.publicOrigin}`);
});

async function shutdown(signal) {
  console.log(`${signal} received, shutting down.`);
  server.close(async () => {
    if (redis) await redis.quit();
    process.exit(0);
  });
  setTimeout(() => process.exit(1), 10_000).unref();
}

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));
