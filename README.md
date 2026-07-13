# Accounts KodingYuk

Implementasi final V1 layanan identitas publik dan SSO KodingYuk untuk
`accounts.kodingyuk.id`.

Repositori ini berisi dua komponen yang sengaja dipisahkan:

- `odoo_addons/kodingyuk_accounts`: model akun publik, relasi siswa, consent,
  registry OIDC client, dan API server-to-server.
- `web`: website register/login sekaligus OpenID Provider (OIDC) untuk seluruh
  produk KodingYuk.

## Dokumen

- [Product Requirements Document](docs/PRD.md)
- [Audit Repository dan Kondisi Saat Ini](docs/REPOSITORY-AUDIT.md)
- [Panduan Deployment](docs/DEPLOYMENT.md)
- [Instalasi Final V1 dan Informasi yang Dibutuhkan](docs/INSTALLATION.md)
- [Security Audit Log](docs/AUDIT-LOG.md)
- [Panduan Integrasi Produk](docs/PRODUCT-INTEGRATION.md)

## Keputusan inti

- Odoo tetap menjadi aplikasi internal tim KodingYuk.
- Pengguna publik/siswa tidak dibuat sebagai `res.users`.
- Akun eksternal memakai model khusus `ky.account`, mengikuti pola `ky.client`
  pada KodyHost dan `lms.user` pada TechLearn.
- Data master siswa tetap menggunakan `m.siswa`; tidak dibuat tabel siswa baru.
- `m.siswa.access_code` dengan prefix `ST-` tetap dipakai sebagai kode aktivasi,
  penautan akun, dan fallback selama migrasi.
- Aplikasi produk memakai SSO melalui OpenID Connect; data project/game tetap
  berada di penyimpanan masing-masing produk.

## Menjalankan web secara lokal

```powershell
cd web
Copy-Item .env.example .env
npm install
npm test
npm start
```

Discovery OIDC tersedia di
`http://localhost:3000/.well-known/openid-configuration`. Untuk produksi,
Redis, HTTPS, signing key tetap, dan secret API Odoo wajib dikonfigurasi.
