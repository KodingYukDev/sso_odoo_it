# Audit Repository untuk Accounts KodingYuk

**Tanggal audit:** 13 Juli 2026
**Workspace:** `D:\Aril Saputra\Project`
**Cakupan:** inventarisasi seluruh 71 folder tingkat atas yang sudah ada sebelum
folder `accounts-kodingyuk` dibuat, pencarian lintas-repo
untuk autentikasi/siswa, lalu pembacaan mendalam pada implementasi yang relevan.

Audit ini bukan code review menyeluruh setiap baris. Seluruh project telah masuk
inventaris dan pencarian lintas-repo; pembacaan kode rinci difokuskan pada project
yang menyimpan identitas, melakukan login/register, atau akan menjadi client SSO.

## Temuan utama

### 1. Database siswa dan kode siswa sudah ada

Sumber: `students/models/m_siswa.py` dan
`students/controllers/student_api.py`.

- Master siswa adalah model Odoo `m.siswa`.
- Field identitas/akses yang sudah ada:
  - `nis`: nomor induk siswa, saat ini tidak diwajibkan dan tidak terlihat memiliki
    generator unik di repository.
  - `access_code`: kode akses dashboard dengan prefix `ST-`.
  - `access_code_active`: status aktif kode akses.
- Kode `ST-` dibuat di level siswa sehingga berlaku lintas enrollment.
- Masih ada `access_code` pada `siswa.kursus.enrollment` untuk kompatibilitas
  implementasi lama.
- Student Dashboard telah login langsung memakai kode tersebut.

Implikasi: Accounts KodingYuk tidak boleh membuat tabel siswa atau format kode
siswa baru. `m.siswa` tetap source of truth. PRD membedakan `nis` sebagai nomor
bisnis siswa dan `access_code` sebagai secret akses/aktivasi yang bisa dirotasi.

### 2. Terdapat jalur publik yang masih membuat `res.users`

`students/controllers/student_api.py` memiliki endpoint `/api/v1/auth/register`
yang membuat `res.partner` dan `res.users` portal. Endpoint login pasangannya
mengautentikasi melalui session Odoo.

Ini bertentangan dengan target arsitektur baru: `res.users` dipertahankan untuk
staff/internal Odoo, sedangkan endpoint register publik tersebut harus
didepresiasi setelah Accounts KodingYuk tersedia.

### 3. Field password langsung pada `m.siswa`

`students/models/m_siswa.py` memiliki field `password = fields.Char(...)`.
Repository yang diaudit tidak menunjukkan hashing atau pemakaian field ini untuk
login Student Dashboard. Field ini tidak boleh dipakai oleh SSO dan perlu
dimigrasikan/dihapus melalui pekerjaan keamanan tersendiri setelah audit data
production.

### 4. KodyHost sudah memiliki pola akun eksternal yang tepat

Implementasi aktif berada di `ky-dev` dan `ky-dev-odoo`, bukan folder `KodyHost`
yang hanya berisi dokumen/generator dokumen.

- Model `ky.client` terpisah dari `res.users`.
- Password disimpan sebagai hash `pbkdf2_sha512`.
- Terhubung ke `res.partner` untuk billing/CRM.
- Frontend memakai NextAuth/Auth.js, Credentials, dan Google.
- KodyHost menyimpan session JWT di frontend dan memanggil endpoint Odoo.

Pola ini menjadi dasar `ky.account`, tetapi `ky.client` tidak langsung dijadikan
akun global karena modelnya membawa konsep dan relasi khusus hosting.

### 5. TechLearn memiliki silo akun kedua

`learning area/techlearn/kodingyuk_lms/models/lms_user.py` mendefinisikan
`lms.user`, juga terpisah dari `res.users`, dengan password hash, verifikasi email,
Google UID, JWT, dan shadow `res.partner` untuk billing.

Secara keamanan dan bentuk model, ini kandidat terbaik kedua untuk menjadi bahan
migrasi. Namun membiarkan `lms.user`, `ky.client`, dan akun baru berjalan sendiri
akan tetap menghasilkan tiga password dan tiga identitas untuk orang yang sama.

### 6. Aplikasi produk memiliki mekanisme login yang berbeda-beda

| Project/kelompok | Kondisi saat audit | Dampak SSO |
|---|---|---|
| `student_dashboard` | Login `ST-` langsung ke API Odoo; kode disimpan di SharedPreferences | Migrasi ke authorization code + PKCE; `ST-` menjadi aktivasi/fallback |
| `ky_labs` | Kode akses divalidasi melalui Firebase dan state disimpan di localStorage | Ganti dengan OIDC; role/program menjadi entitlement |
| `kodyblocksjr-2026` | Guest/offline via IndexedDB; fase kode siswa + Firebase sudah direncanakan tetapi ditunda | Ganti rencana relay khusus dengan SSO pusat dan cloud project API |
| `kodyblocks` | Editor Scratch-derived; hook login/save server masih berupa kontrak dari GUI | Integrasikan adapter OIDC dan project service tanpa menaruh project di Odoo |
| `ky-dev` + `ky-dev-odoo` | Akun `ky.client`, Google/Credentials, JWT frontend | Migrasikan/link ke `ky.account`; service hosting tetap di model KodyHost |
| TechLearn/LMS v2 | Akun `lms.user`, JWT sendiri, register dan Google sendiri | Migrasikan/link ke `ky.account`; enrollment tetap di LMS |
| `kodingyuk-landing-page-cms` | Memiliki login/register sendiri yang terhubung Odoo | Arahkan login/register ke Accounts KodingYuk |
| `lms-edutrack-nextjs` | Verifikasi siswa memakai ID/tanggal lahir dan akses Odoo | Gunakan subject akun; hentikan penggunaan data lahir sebagai credential |
| `kodyverse` | Prototype menyimpan scene lokal dan memakai identity header lingkungan hosting | Integrasi KodingYuk SSO saat menjadi produk publik mandiri |
| Project internal (trainer, finance, admin, CEO, helpdesk, HR) | Mayoritas login Odoo/Google/NextAuth untuk staff | Di luar scope fase publik; jangan dicampur dengan akun siswa |

### 7. Project yang tidak relevan langsung tetap diinventarisasi

Seluruh folder tingkat atas ikut dipindai. Modul HR/finance, Tunas, aplikasi
personal, library pihak ketiga, arsip release, prototipe kosong, asset module, dan
utility tidak menjadi client SSO fase awal karena tidak menghadapi siswa/publik
atau tidak mempunyai runtime autentikasi yang relevan.

## Kesimpulan audit

Masalah utama bukan ketiadaan database siswa, melainkan fragmentasi identity:

```text
m.siswa.access_code + res.users portal + ky.client + lms.user + Firebase codes
```

Accounts KodingYuk harus menjadi lapisan identitas tunggal di atas data yang sudah
ada. Migrasi dilakukan dengan menautkan record lama ke `ky.account`, bukan
menyalin ulang master siswa atau memindahkan seluruh data produk ke satu tabel.
