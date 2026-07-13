# Accounts Service API Contract

API ini hanya untuk komunikasi server-to-server antara `sso_js_it` dan Odoo.
Browser atau aplikasi produk tidak boleh memanggil endpoint ini langsung.

## Authentication

Semua endpoint selain health membutuhkan header:

```http
X-Accounts-Key: <accounts.api_key>
Content-Type: application/json
```

Secret dibandingkan secara constant-time. Gunakan jaringan privat atau allowlist
reverse proxy sebagai lapisan tambahan.

## Endpoint

| Method | Path | Fungsi |
|---|---|---|
| GET | `/accounts/v1/health` | Status konfigurasi service |
| POST | `/accounts/v1/register` | Register akun pending, consent, dan email verification |
| POST | `/accounts/v1/authenticate` | Verifikasi identifier/password |
| POST | `/accounts/v1/account/claims` | Mengambil claim OIDC berdasarkan subject UUID |
| POST | `/accounts/v1/email/verification/request` | Kirim ulang email verifikasi |
| POST | `/accounts/v1/email/verify` | Konsumsi token verifikasi |
| POST | `/accounts/v1/password/reset/request` | Antrekan email reset secara non-enumerating |
| POST | `/accounts/v1/password/reset` | Konsumsi token dan ganti password |
| POST | `/accounts/v1/student/claim` | Buat link akun ke `m.siswa` |
| POST | `/accounts/v1/consent` | Catat grant/revoke consent |
| POST | `/accounts/v1/audit` | Terima event OIDC terkontrol dari JS service |
| GET | `/accounts/v1/oidc/clients` | Registry public OIDC client aktif |

Response sukses:

```json
{"success": true}
```

Response gagal:

```json
{
  "success": false,
  "error": "machine_readable_code",
  "message": "Safe public message"
}
```

## Data sensitif

Password, kode ST, token verifikasi/reset, authorization code, dan OAuth token
tidak boleh masuk log. Context audit memakai properti `_audit` dan hanya membawa
request ID, IP, user-agent, source, serta client ID.

Perubahan breaking harus membuat versi route baru (`/accounts/v2/...`) agar
service JS dapat dimigrasikan tanpa downtime.
