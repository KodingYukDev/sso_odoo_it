# Instalasi Final V1 — KodingYuk Account

Dokumen ini memasang dua service: addon Odoo untuk sumber data akun publik dan
web `accounts.kodingyuk.id` sebagai OpenID Provider. Lakukan pertama kali di
staging dengan salinan database, bukan langsung di production.

## Informasi yang perlu disiapkan owner

| Informasi | Contoh/keputusan yang dibutuhkan |
|---|---|
| Domain | Konfirmasi `accounts.kodingyuk.id` dan akses mengubah DNS |
| Odoo | URL internal, nama database staging/production, lokasi custom addons, cara restart service |
| Email | SMTP host, port, TLS, username/password, dan sender terverifikasi seperti `account@kodingyuk.id` |
| Legal | URL Ketentuan Layanan, URL Kebijakan Privasi, dan versi dokumen/policy |
| Infrastruktur | Server/Coolify project untuk web, Redis, serta akses memasang environment secrets |
| Aplikasi client | Nama produk, client ID, exact callback URL, dan post-logout URL masing-masing |
| Claim siswa | Untuk V1: approval admin (disarankan) atau mengaktifkan ST-only direct claim |
| Retention audit | Jumlah hari penyimpanan audit; default 365 hari, minimum 30 hari |
| Pilot | Produk pertama yang dialihkan; disarankan website ujian staging sebelum KodyHost/KodyBlocks |

Jangan kirim password SMTP, API key, signing JWKS, atau akses server melalui
dokumen/commit. Masukkan langsung ke secret manager/Coolify environment.

## Prasyarat

- Odoo 17 dengan addon `students` terpasang dan model `m.siswa` tersedia.
- Node.js 22 LTS atau lebih baru bila berjalan tanpa Docker.
- Redis persisten.
- Reverse proxy dan sertifikat HTTPS valid.
- Outgoing Mail Server Odoo yang sudah dites.
- Backup database Odoo yang restorasinya pernah diuji.

## A. Install addon Odoo

1. Backup database Odoo.
2. Salin folder berikut ke custom addons Odoo:

   `accounts-kodingyuk/odoo_addons/kodingyuk_accounts`

3. Pastikan parent folder berada pada `addons_path`, lalu restart Odoo.
4. Aktifkan developer mode, buka **Apps → Update Apps List**.
5. Cari **KodingYuk Accounts**, lalu install.
6. Buka **Settings → KodingYuk Accounts** dan isi:

   - Public Accounts URL: `https://accounts.kodingyuk.id`
   - Service API Key: random secret minimal 32 byte
   - Security Email Sender: sender SMTP terverifikasi
   - Direct Student Claim: tetap mati untuk V1
   - Audit Log Retention: `365` hari atau sesuai kebijakan legal

CLI staging alternatif:

```bash
odoo-bin -d NAMA_DATABASE -u kodingyuk_accounts --stop-after-init
```

Modul hanya menambah model `ky.*` dan kontak CRM bila diperlukan. Modul tidak
membuat akun publik sebagai `res.users` serta tidak menghapus/mengubah record
`m.siswa` lama.

## B. Konfigurasi email Odoo

1. Buat/test **Outgoing Mail Server** di Odoo.
2. Pastikan sender pada Settings diizinkan SMTP provider.
3. Pastikan SPF, DKIM, dan DMARC domain sudah benar.
4. Pastikan scheduled action Mail Queue Manager aktif.
5. Uji register staging dan pastikan email verifikasi diterima.

Email verifikasi berlaku 24 jam. Token reset password berlaku 30 menit. Keduanya
sekali pakai dan hanya hash token yang disimpan pada `ky.account.token`.

## C. Daftarkan OIDC client

Buka **KodingYuk Accounts → OIDC Clients**. Buat satu record per produk. Contoh:

```text
Name: Student Exam Staging
Client ID: student-exam-staging
Redirect URIs: https://ujian-staging.kodingyuk.id/auth/callback
Post Logout Redirect URIs: https://ujian-staging.kodingyuk.id/
Status: Active
Public Client: aktif
```

Gunakan exact HTTPS URI tanpa wildcard. Setelah menambah/mengubah client,
restart web Accounts karena registry dibaca ketika service mulai.

## D. Deploy web Accounts

Di folder `web`:

```powershell
Copy-Item .env.example .env
npm install
npm test
npm run generate:jwks
```

Simpan output JWKS sebagai secret `OIDC_JWKS`; jangan dimasukkan ke Git. Buat
dua cookie key random minimal 32 karakter dan satu API key yang sama dengan Odoo.

Environment production wajib:

```dotenv
NODE_ENV=production
PORT=3000
PUBLIC_ORIGIN=https://accounts.kodingyuk.id
ODOO_BASE_URL=https://URL-ODOO-INTERNAL
ODOO_ACCOUNTS_API_KEY=SECRET-YANG-SAMA-DENGAN-ODOO
REDIS_URL=redis://redis:6379/0
COOKIE_KEYS=SECRET-LAMA,SECRET-AKTIF
OIDC_JWKS={"keys":[...]}
OIDC_CLIENTS_JSON=[]
POLICY_VERSION=VERSI-LEGAL-YANG-DISETUJUI
TERMS_URL=https://kodingyuk.id/terms
PRIVACY_URL=https://kodingyuk.id/privacy
TRUST_PROXY=1
```

Deploy dengan Docker Compose:

```powershell
docker compose up -d --build
```

Untuk Coolify, gunakan folder `accounts-kodingyuk/web`, pilih Dockerfile atau
Compose, masukkan environment sebagai secrets, expose port 3000, dan pasang
domain `accounts.kodingyuk.id` dengan HTTPS.

## E. Verifikasi setelah install

1. `/health` mengembalikan HTTP 200.
2. `/.well-known/openid-configuration` mempunyai issuer yang persis sama dengan
   `https://accounts.kodingyuk.id`.
3. Discovery memuat PKCE `S256`.
4. Register membuat `ky.account` status pending dan tidak menambah `res.users`.
5. Email verifikasi mengaktifkan akun.
6. Login OIDC kembali ke exact callback aplikasi.
7. Reset password berhasil dan token kedua kali ditolak.
8. Kode ST membuat student link pending; manager memverifikasi link dengan metode
   Admin Approval setelah pemeriksaan data.
9. Login internal Odoo pada `/web/login` tetap berjalan seperti sebelumnya.
10. Data/project/login legacy masih dapat dipakai selama fase dual-read.
11. Menu **Audit Logs** menampilkan register, login, verification, reset, claim,
    consent, serta OIDC event tanpa password/token/kode ST.

## F. Go-live dan rollback

- Alihkan satu produk staging lebih dahulu.
- Jangan menonaktifkan login legacy sebelum rekonsiliasi user/project selesai.
- Rollback dilakukan dengan mengembalikan tombol login produk ke legacy dan
  menghentikan redirect SSO. Jangan uninstall addon Odoo karena uninstall akan
  menghapus tabel milik modul.
- Simpan `OIDC_JWKS` lama selama masih ada token/sesi yang ditandatangani key itu.
- Rotasi cookie key dengan menaruh key baru di depan dan mempertahankan key lama
  sementara waktu.
