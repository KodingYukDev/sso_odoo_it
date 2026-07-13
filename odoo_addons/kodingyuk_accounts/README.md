# KodingYuk Accounts — Odoo 17 addon

Modul sumber data akun publik untuk KodingYuk Account. Modul ini tidak membuat
`res.users` saat publik mendaftar.

## Model

- `ky.account`: identitas publik dan password hash.
- `ky.account.student.link`: relasi many-to-many ke `m.siswa` yang sudah ada.
- `ky.account.consent`: bukti consent append-only.
- `ky.account.identity`: identitas sosial atau legacy.
- `ky.oidc.client`: registry aplikasi yang boleh memakai SSO.

## Parameter sistem wajib

- `accounts.api_key`: secret acak yang sama dengan
  `ODOO_ACCOUNTS_API_KEY` pada web SSO.
- `accounts.public_origin`: `https://accounts.kodingyuk.id`.
- `accounts.email_from`: sender yang sudah diverifikasi pada SMTP Odoo.
- `accounts.allow_direct_student_claim`: default `False`. Jangan aktifkan di
  production sebelum metode verifikasi tambahan siswa/wali disepakati.

Tambahkan folder `odoo_addons` ke `addons_path`, update Apps List, lalu install
`KodingYuk Accounts`. Modul bergantung pada modul `students` karena sumber data
siswa tetap `m.siswa`.

Parameter tersebut juga tersedia melalui **Settings → KodingYuk Accounts**.
