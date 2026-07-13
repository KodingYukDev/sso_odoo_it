# Instalasi Addon KodingYuk Accounts

## Prasyarat

- Odoo 17.
- Addon existing `students` tersedia dan model `m.siswa` dapat diakses.
- Outgoing Mail Server Odoo aktif.
- Backup database dan staging database untuk uji upgrade.
- URL serta API key untuk service web
  [`sso_js_it`](https://github.com/KodingYukDev/sso_js_it).

## 1. Clone langsung ke extra-addons

```bash
cd /mnt/extra-addons
git clone https://github.com/KodingYukDev/sso_odoo_it.git
```

Struktur hasil clone harus seperti berikut:

```text
/mnt/extra-addons/sso_odoo_it/
├── __init__.py
├── __manifest__.py
├── controllers/
├── models/
├── security/
└── views/
```

Tambahkan parent folder ke konfigurasi Odoo:

```ini
addons_path = /usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons
```

## 2. Install di staging

```bash
odoo-bin \
  -c /etc/odoo/odoo.conf \
  -d NAMA_DATABASE_STAGING \
  -i sso_odoo_it \
  --stop-after-init
```

Atau buka **Apps → Update Apps List**, cari **KodingYuk Accounts**, lalu install.

## 3. Isi Settings

Buka **KodingYuk Accounts → Settings**:

| Setting | Nilai |
|---|---|
| Public Accounts URL | `https://account.kodingyuk.id` |
| Service API Key | Random secret minimal 32 byte; sama dengan `ODOO_ACCOUNTS_API_KEY` pada JS |
| Security Email Sender | Contoh `account@kodingyuk.id`, harus diterima SMTP |
| Direct Student Claim | Nonaktif untuk production V1 |
| Audit Retention | Default 365 hari, minimum 30 hari |

Jangan menyimpan API key pada Git atau dokumentasi.

## 4. Konfigurasi email

1. Buat dan tes **Outgoing Mail Server** Odoo.
2. Pastikan sender pada Settings diizinkan SMTP provider.
3. Aktifkan scheduled action pengiriman antrean email.
4. Pastikan SPF, DKIM, dan DMARC domain benar.

Email verifikasi berlaku 24 jam. Token reset password berlaku 30 menit. Token
hanya disimpan sebagai hash dan mail record dihapus otomatis setelah terkirim.

## 5. Daftarkan OIDC client

Buka **KodingYuk Accounts → OIDC Clients**. Gunakan satu client per produk dan
exact HTTPS callback URI tanpa wildcard.

```text
Name: Student Exam Staging
Client ID: student-exam-staging
Redirect URIs: https://ujian-staging.kodingyuk.id/auth/callback
Post Logout Redirect URIs: https://ujian-staging.kodingyuk.id/
Public Client: aktif
Status: Active
```

Restart service `sso_js_it` setelah registry client berubah karena registry
dibaca ketika service mulai.

## 6. Acceptance test

1. Register publik membuat `ky.account` pending dan tidak menambah `res.users`.
2. Email verifikasi mengaktifkan akun.
3. Login serta reset password berhasil.
4. Kode ST membuat student link pending untuk approval admin.
5. Audit Logs mencatat register/login/verification/reset/OIDC event.
6. Login internal `/web/login` tetap berjalan.
7. `m.siswa`, enrollment, NIS, kode ST, dan data lama tidak berubah.

## Update

```bash
cd /mnt/extra-addons/sso_odoo_it
git pull --ff-only origin main

odoo-bin \
  -c /etc/odoo/odoo.conf \
  -d NAMA_DATABASE \
  -u sso_odoo_it \
  --stop-after-init
```

Jalankan update di staging terlebih dahulu. Rollback dilakukan dengan kembali ke
commit sebelumnya dan menjalankan upgrade modul; jangan uninstall modul karena
uninstall akan menghapus tabel milik addon.
