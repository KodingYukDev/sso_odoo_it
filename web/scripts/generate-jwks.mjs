import { randomUUID } from 'node:crypto';
import { exportJWK, generateKeyPair } from 'jose';

const { privateKey } = await generateKeyPair('RS256', { extractable: true });
const key = await exportJWK(privateKey);
process.stdout.write(`${JSON.stringify({
  keys: [{ ...key, kid: randomUUID(), use: 'sig', alg: 'RS256' }],
})}\n`);
