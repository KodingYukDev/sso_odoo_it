export class OdooApiError extends Error {
  constructor(message, { status = 500, code = 'odoo_error', cause } = {}) {
    super(message, { cause });
    this.name = 'OdooApiError';
    this.status = status;
    this.code = code;
  }
}

export class OdooAccountsClient {
  constructor({ baseUrl, apiKey, fetchImpl = globalThis.fetch, timeoutMs = 8000 }) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
    this.apiKey = apiKey;
    this.fetchImpl = fetchImpl;
    this.timeoutMs = timeoutMs;
  }

  async request(path, { method = 'GET', body } = {}) {
    let response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        method,
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
          'X-Accounts-Key': this.apiKey,
        },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(this.timeoutMs),
      });
    } catch (error) {
      throw new OdooApiError('Layanan data akun sedang tidak tersedia.', {
        status: 503,
        code: 'odoo_unavailable',
        cause: error,
      });
    }

    let payload;
    try {
      payload = await response.json();
    } catch {
      throw new OdooApiError('Respons layanan data akun tidak valid.', {
        status: 502,
        code: 'invalid_odoo_response',
      });
    }
    if (!response.ok || !payload.success) {
      throw new OdooApiError(payload.message || 'Permintaan akun gagal.', {
        status: response.status,
        code: payload.error || 'odoo_error',
      });
    }
    return payload;
  }

  register(data) { return this.request('/accounts/v1/register', { method: 'POST', body: data }); }
  authenticate(identifier, password, audit = {}) {
    return this.request('/accounts/v1/authenticate', {
      method: 'POST', body: { identifier, password, _audit: audit },
    });
  }
  claims(subjectUuid) {
    return this.request('/accounts/v1/account/claims', { method: 'POST', body: { subject_uuid: subjectUuid } });
  }
  claimStudent(subjectUuid, accessCode, relationship = 'self', audit = {}) {
    return this.request('/accounts/v1/student/claim', {
      method: 'POST',
      body: { subject_uuid: subjectUuid, access_code: accessCode, relationship, _audit: audit },
    });
  }
  recordConsent(subjectUuid, data) {
    return this.request('/accounts/v1/consent', {
      method: 'POST', body: { subject_uuid: subjectUuid, ...data },
    });
  }
  requestEmailVerification(identifier, audit = {}) {
    return this.request('/accounts/v1/email/verification/request', {
      method: 'POST', body: { identifier, _audit: audit },
    });
  }
  verifyEmail(token, audit = {}) {
    return this.request('/accounts/v1/email/verify', {
      method: 'POST', body: { token, _audit: audit },
    });
  }
  requestPasswordReset(identifier, audit = {}) {
    return this.request('/accounts/v1/password/reset/request', {
      method: 'POST', body: { identifier, _audit: audit },
    });
  }
  resetPassword(token, password, audit = {}) {
    return this.request('/accounts/v1/password/reset', {
      method: 'POST', body: { token, password, _audit: audit },
    });
  }
  audit({ event, outcome, subjectUuid = '', clientId = '', details = {}, context = {} }) {
    return this.request('/accounts/v1/audit', {
      method: 'POST',
      body: {
        event, outcome, subject_uuid: subjectUuid, client_id: clientId,
        details, _audit: context,
      },
    });
  }
  async clients() { return (await this.request('/accounts/v1/oidc/clients')).clients; }
}
