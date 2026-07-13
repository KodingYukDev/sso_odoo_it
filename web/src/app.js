import express from 'express';
import { randomUUID } from 'node:crypto';
import rateLimit from 'express-rate-limit';
import helmet from 'helmet';

import { OdooApiError } from './odoo-client.js';
import {
  consentView, homeView, loginView, registerView, successView,
  messageView, requestLinkView, tokenConfirmationView,
} from './views.js';

function noStore(_req, res, next) {
  res.set('Cache-Control', 'no-store');
  next();
}

export function sameOrigin(publicOrigin) {
  return (req, res, next) => {
    const source = req.get('origin') || req.get('referer');
    if (!source) return res.status(403).send('Missing request origin');
    try {
      if (new URL(source).origin !== publicOrigin) return res.status(403).send('Invalid request origin');
    } catch {
      return res.status(403).send('Invalid request origin');
    }
    return next();
  };
}

function friendlyError(error) {
  if (error instanceof OdooApiError) {
    if (error.code === 'invalid_credentials') return 'Email/username atau password tidak cocok.';
    if (error.code === 'email_not_verified') return 'Email belum diverifikasi. Periksa inbox atau kirim ulang link verifikasi.';
    if (error.code === 'invalid_token') return 'Link sudah tidak berlaku atau telah digunakan.';
    if (error.code === 'already_exists') return 'Email atau username sudah terdaftar.';
    if (error.code === 'claim_failed') return 'Kode siswa belum dapat ditautkan. Akun tetap bisa digunakan.';
    return error.message;
  }
  return 'Terjadi kendala. Silakan coba lagi.';
}

function valuesFrom(body) {
  return Object.fromEntries(['name', 'email', 'username', 'student_code'].map((key) => [key, body[key] || '']));
}

function auditContext(req, clientId = '') {
  return {
    request_id: req.get('x-request-id') || randomUUID(),
    ip_address: req.ip || '',
    user_agent: req.get('user-agent') || '',
    source: 'accounts_web',
    client_id: clientId,
  };
}

export function createApp({ config, odoo, provider, logger = console }) {
  const app = express();
  app.set('trust proxy', config.TRUST_PROXY);
  app.disable('x-powered-by');
  app.use(helmet({
    contentSecurityPolicy: {
      directives: {
        defaultSrc: ["'none'"], styleSrc: ["'unsafe-inline'"], formAction: ["'self'"],
        frameAncestors: ["'none'"], baseUri: ["'none'"], imgSrc: ["'self'", 'data:'],
      },
    },
    referrerPolicy: { policy: 'same-origin' },
  }));
  const formParser = express.urlencoded({ extended: false, limit: '32kb' });
  app.use(rateLimit({ windowMs: 60_000, limit: 180, standardHeaders: 'draft-8', legacyHeaders: false }));

  const authLimiter = rateLimit({
    windowMs: 15 * 60_000, limit: 20, standardHeaders: 'draft-8', legacyHeaders: false,
    message: 'Terlalu banyak percobaan. Tunggu beberapa menit lalu coba lagi.',
  });
  const verifyOrigin = sameOrigin(config.publicOrigin);

  app.get('/', (_req, res) => res.type('html').send(homeView()));
  app.get('/health', (_req, res) => res.json({ status: 'ok', service: 'accounts-web' }));

  app.get('/register', noStore, async (req, res, next) => {
    try {
      if (req.query.uid) await provider.interactionDetails(req, res);
      res.type('html').send(registerView({
        uid: req.query.uid || '', termsUrl: config.TERMS_URL, privacyUrl: config.PRIVACY_URL,
      }));
    } catch (error) { next(error); }
  });

  app.post('/register', noStore, verifyOrigin, authLimiter, formParser, async (req, res) => {
    const uid = req.query.uid || '';
    const values = valuesFrom(req.body);
    try {
      if (uid) await provider.interactionDetails(req, res);
      if (req.body.accept_policy !== 'yes') {
        return res.status(400).type('html').send(registerView({
          uid, values, termsUrl: config.TERMS_URL, privacyUrl: config.PRIVACY_URL,
          error: 'Ketentuan dan Kebijakan Privasi wajib disetujui.',
        }));
      }
      const { account } = await odoo.register({
        name: req.body.name, email: req.body.email, username: req.body.username,
        password: req.body.password, source: 'accounts_web', accept_policy: true,
        marketing: req.body.marketing === 'yes', policy_version: config.POLICY_VERSION,
        evidence_ref: `web:${new Date().toISOString()}`, _audit: auditContext(req),
      });

      if (req.body.student_code) {
        try { await odoo.claimStudent(account.sub, req.body.student_code, 'self', auditContext(req)); }
        catch (error) { logger.warn(`Student claim deferred for ${account.sub}: ${error.message}`); }
      }
      return res.status(201).type('html').send(successView(
        'Registrasi berhasil. Periksa email untuk mengaktifkan akun, lalu buka kembali aplikasi asal.',
      ));
    } catch (error) {
      logger.warn(`Registration failed: ${error.message}`);
      return res.status(error.status && error.status < 500 ? error.status : 503).type('html')
        .send(registerView({
          uid, values, error: friendlyError(error),
          termsUrl: config.TERMS_URL, privacyUrl: config.PRIVACY_URL,
        }));
    }
  });

  app.get('/interaction/:uid', noStore, async (req, res, next) => {
    try {
      const details = await provider.interactionDetails(req, res);
      const client = await provider.Client.find(details.params.client_id);
      const clientName = client?.clientName || details.params.client_id;
      if (details.prompt.name === 'login') {
        return res.type('html').send(loginView({ uid: details.uid, clientName }));
      }
      if (details.prompt.name === 'consent') {
        return res.type('html').send(consentView({ uid: details.uid, clientName, details: details.prompt.details }));
      }
      return res.status(501).send('Interaction not supported');
    } catch (error) { return next(error); }
  });

  app.post('/interaction/:uid/login', noStore, verifyOrigin, authLimiter, formParser, async (req, res, next) => {
    try {
      const details = await provider.interactionDetails(req, res);
      if (details.prompt.name !== 'login') return res.status(400).send('Invalid interaction');
      const { account } = await odoo.authenticate(
        req.body.identifier, req.body.password, auditContext(req, details.params.client_id),
      );
      if (req.body.student_code) {
        try {
          await odoo.claimStudent(
            account.sub, req.body.student_code, 'self', auditContext(req, details.params.client_id),
          );
        }
        catch (error) { logger.warn(`Student claim deferred for ${account.sub}: ${error.message}`); }
      }
      return provider.interactionFinished(req, res, { login: { accountId: account.sub } }, { mergeWithLastSubmission: false });
    } catch (error) {
      if (!(error instanceof OdooApiError)) return next(error);
      let clientName = 'aplikasi KodingYuk';
      try {
        const details = await provider.interactionDetails(req, res);
        const client = await provider.Client.find(details.params.client_id);
        clientName = client?.clientName || clientName;
      } catch { /* interaction error is handled by the next attempt */ }
      return res.status(error.status === 401 ? 401 : 503).type('html').send(loginView({
        uid: req.params.uid, clientName, error: friendlyError(error), identifier: req.body.identifier,
        needsVerification: error.code === 'email_not_verified',
      }));
    }
  });

  app.post('/interaction/:uid/confirm', noStore, verifyOrigin, formParser, async (req, res, next) => {
    try {
      const { prompt, grantId, session, params } = await provider.interactionDetails(req, res);
      if (prompt.name !== 'consent') return res.status(400).send('Invalid interaction');
      let grant = grantId ? await provider.Grant.find(grantId) : new provider.Grant({
        accountId: session.accountId, clientId: params.client_id,
      });
      if (prompt.details.missingOIDCScope) grant.addOIDCScope(prompt.details.missingOIDCScope.join(' '));
      if (prompt.details.missingOIDCClaims) grant.addOIDCClaims(prompt.details.missingOIDCClaims);
      if (prompt.details.missingResourceScopes) {
        for (const [indicator, scopes] of Object.entries(prompt.details.missingResourceScopes)) {
          grant.addResourceScope(indicator, scopes.join(' '));
        }
      }
      return provider.interactionFinished(req, res, { consent: { grantId: await grant.save() } });
    } catch (error) { return next(error); }
  });

  app.post('/interaction/:uid/abort', noStore, verifyOrigin, formParser, async (req, res, next) => {
    try {
      await provider.interactionDetails(req, res);
      return provider.interactionFinished(req, res, {
        error: 'access_denied', error_description: 'Pengguna membatalkan proses masuk.',
      }, { mergeWithLastSubmission: false });
    } catch (error) { return next(error); }
  });

  app.get('/verify-email', noStore, (req, res) => res.type('html').send(tokenConfirmationView({
    kind: 'verify', token: req.query.token || '',
  })));
  app.post('/verify-email', noStore, verifyOrigin, authLimiter, formParser, async (req, res) => {
    try {
      await odoo.verifyEmail(req.body.token, auditContext(req));
      return res.type('html').send(messageView({
        title: 'Email berhasil diverifikasi', message: 'Akun sudah aktif. Kembali ke produk dan masuk dengan KodingYuk Account.',
      }));
    } catch (error) {
      return res.status(400).type('html').send(tokenConfirmationView({
        kind: 'verify', token: req.body.token, error: friendlyError(error),
      }));
    }
  });

  app.get('/forgot-password', noStore, (_req, res) => res.type('html').send(requestLinkView({ kind: 'reset' })));
  app.post('/forgot-password', noStore, verifyOrigin, authLimiter, formParser, async (req, res) => {
    try { await odoo.requestPasswordReset(req.body.identifier, auditContext(req)); }
    catch (error) { logger.warn(`Password reset request failed: ${error.message}`); }
    return res.type('html').send(requestLinkView({ kind: 'reset', identifier: req.body.identifier, sent: true }));
  });

  app.get('/reset-password', noStore, (req, res) => res.type('html').send(tokenConfirmationView({
    kind: 'reset', token: req.query.token || '',
  })));
  app.post('/reset-password', noStore, verifyOrigin, authLimiter, formParser, async (req, res) => {
    try {
      await odoo.resetPassword(req.body.token, req.body.password, auditContext(req));
      return res.type('html').send(messageView({
        title: 'Password berhasil diubah', message: 'Gunakan password baru saat masuk dari produk KodingYuk.',
      }));
    } catch (error) {
      return res.status(400).type('html').send(tokenConfirmationView({
        kind: 'reset', token: req.body.token, error: friendlyError(error),
      }));
    }
  });

  app.get('/resend-verification', noStore, (req, res) => res.type('html').send(requestLinkView({
    kind: 'verify', identifier: req.query.identifier || '',
  })));
  app.post('/resend-verification', noStore, verifyOrigin, authLimiter, formParser, async (req, res) => {
    try { await odoo.requestEmailVerification(req.body.identifier, auditContext(req)); }
    catch (error) { logger.warn(`Verification resend failed: ${error.message}`); }
    return res.type('html').send(requestLinkView({ kind: 'verify', identifier: req.body.identifier, sent: true }));
  });

  app.use(provider.callback());
  app.use((error, _req, res, _next) => {
    logger.error(error);
    if (res.headersSent) return;
    res.status(500).type('text').send('Proses masuk tidak dapat dilanjutkan. Silakan mulai lagi dari aplikasi asal.');
  });
  return app;
}
