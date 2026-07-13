# KodingYuk Accounts — Odoo Addon

Addon Odoo 17 yang menjadi source of truth untuk akun publik KodingYuk. Akun
publik disimpan pada `ky.account`, bukan `res.users`, sehingga login internal tim
KodingYuk tetap terpisah.

Repository ini sengaja berbentuk satu addon langsung di root agar dapat di-clone
langsung ke `extra-addons/kodingyuk_accounts`.

Service web/OIDC berada di repository terpisah:
[`KodingYukDev/sso_js_it`](https://github.com/KodingYukDev/sso_js_it).

## Model utama

- `ky.account`: akun publik dan password hash.
- `ky.account.token`: token sekali pakai untuk verifikasi email/reset password.
- `ky.account.student.link`: relasi akun ke master existing `m.siswa`.
- `ky.account.consent`: consent append-only.
- `ky.account.audit.log`: security audit trail append-only.
- `ky.account.identity`: mapping identity sosial/legacy.
- `ky.oidc.client`: registry aplikasi OIDC.

## Install cepat

```bash
cd /mnt/extra-addons
git clone https://github.com/KodingYukDev/sso_odoo_it.git kodingyuk_accounts

odoo-bin \
  -c /etc/odoo/odoo.conf \
  -d NAMA_DATABASE \
  -i kodingyuk_accounts \
  --stop-after-init
```

Pastikan `/mnt/extra-addons` tercantum pada `addons_path`, lalu restart Odoo.
Modul existing `students` harus sudah tersedia karena master siswa tetap memakai
`m.siswa` dan kode `ST-` yang sudah ada.

## Update

```bash
cd /mnt/extra-addons/kodingyuk_accounts
git pull --ff-only origin main

odoo-bin \
  -c /etc/odoo/odoo.conf \
  -d NAMA_DATABASE \
  -u kodingyuk_accounts \
  --stop-after-init
```

## Konfigurasi

Buka **KodingYuk Accounts → Settings** dan isi:

- Public Accounts URL: `https://accounts.kodingyuk.id`
- Service API Key: secret server-to-server minimal 32 byte
- Security Email Sender: sender yang sudah diverifikasi pada SMTP Odoo
- Direct Student Claim: nonaktif untuk production V1
- Audit Retention: default 365 hari

## Dokumentasi

- [Instalasi Odoo](docs/INSTALLATION.md)
- [API Contract](docs/API.md)
- [Security Audit Log](docs/AUDIT-LOG.md)
- [PRD dan arsitektur](docs/PRD.md)
