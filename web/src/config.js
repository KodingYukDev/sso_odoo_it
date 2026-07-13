import { z } from 'zod';

const schema = z.object({
  NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),
  PORT: z.coerce.number().int().min(1).max(65535).default(3000),
  PUBLIC_ORIGIN: z.string().url().default('http://localhost:3000'),
  ODOO_BASE_URL: z.string().url().default('http://localhost:8069'),
  ODOO_ACCOUNTS_API_KEY: z.string().min(1).default('development-only-key'),
  REDIS_URL: z.string().url().optional(),
  COOKIE_KEYS: z.string().default('development-cookie-key-change-me'),
  OIDC_JWKS: z.string().optional(),
  OIDC_CLIENTS_JSON: z.string().default('[]'),
  POLICY_VERSION: z.string().min(1).default('2026-07-13'),
  TERMS_URL: z.string().url().default('https://kodingyuk.id/terms'),
  PRIVACY_URL: z.string().url().default('https://kodingyuk.id/privacy'),
  TRUST_PROXY: z.coerce.number().int().min(0).max(10).default(1),
});

function parseJson(value, label) {
  try {
    return JSON.parse(value);
  } catch (error) {
    throw new Error(`${label} must contain valid JSON`, { cause: error });
  }
}

export function loadConfig(env = process.env) {
  const parsed = schema.parse(env);
  const config = {
    ...parsed,
    publicOrigin: new URL(parsed.PUBLIC_ORIGIN).origin,
    odooBaseUrl: parsed.ODOO_BASE_URL.replace(/\/$/, ''),
    cookieKeys: parsed.COOKIE_KEYS.split(',').map((key) => key.trim()).filter(Boolean),
    fallbackClients: parseJson(parsed.OIDC_CLIENTS_JSON, 'OIDC_CLIENTS_JSON'),
    jwks: parsed.OIDC_JWKS ? parseJson(parsed.OIDC_JWKS, 'OIDC_JWKS') : null,
  };

  if (!Array.isArray(config.fallbackClients)) {
    throw new Error('OIDC_CLIENTS_JSON must be a JSON array');
  }
  if (config.NODE_ENV === 'production') {
    if (!config.REDIS_URL) throw new Error('REDIS_URL is required in production');
    if (!config.jwks?.keys?.length) throw new Error('OIDC_JWKS with private keys is required in production');
    if (config.cookieKeys.length < 2 || config.cookieKeys.some((key) => key.length < 32)) {
      throw new Error('Production needs at least two COOKIE_KEYS of 32 characters or more');
    }
    if (config.publicOrigin.startsWith('http://')) {
      throw new Error('PUBLIC_ORIGIN must use HTTPS in production');
    }
  }
  return config;
}
