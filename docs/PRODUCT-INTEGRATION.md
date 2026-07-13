# Integrasi Produk ke KodingYuk Account

## Kontrak OIDC

- Issuer: `https://accounts.kodingyuk.id`
- Discovery: `/.well-known/openid-configuration`
- Flow: Authorization Code
- PKCE: wajib `S256`
- Scope awal: `openid profile email student.basic`
- Identitas penyimpanan: claim `sub`, bukan email, `nis`, `access_code`, atau ID
  database Odoo.

Claim yang tersedia:

| Claim | Makna |
|---|---|
| `sub` | UUID publik stabil dan immutable |
| `name` | Nama tampil |
| `preferred_username` | Username bila ada |
| `email`, `email_verified` | Email dan status verifikasinya |
| `account_type` | public/student/guardian/client |
| `is_student` | Ada link siswa terverifikasi |

Produk tidak mendapat `m.siswa.id`, kode `ST-`, password, data marketing, maupun
akses Odoo. Data game/project tetap berada pada database produk dan cukup diberi
owner `sub`.

## Alur redirect

1. Produk membuat `state`, `nonce`, `code_verifier`, dan `code_challenge` S256.
2. Browser diarahkan ke authorization endpoint issuer.
3. Accounts menampilkan login/register dan consent.
4. Browser kembali ke exact redirect URI dengan `code` dan `state`.
5. Backend/BFF produk menukar `code` + `code_verifier` ke token endpoint.
6. Produk memvalidasi issuer, audience, signature, expiry, nonce, dan state.
7. Produk mengikat data lokal ke `sub`.

Gunakan library OIDC resmi untuk framework produk; jangan merakit validasi token
sendiri. Discovery membuat URL endpoint tidak perlu di-hardcode.

## Migrasi tanpa kehilangan data

Untuk setiap produk:

1. Tambah kolom nullable `account_sub` atau tabel identity mapping; jangan rename
   atau drop primary key user lama.
2. Saat user lama login, tautkan identity lama ke `sub` setelah verifikasi.
3. Baca data memakai `account_sub`; bila kosong fallback ke identity lama.
4. Tulis data baru ke ownership baru sekaligus pertahankan foreign key lama pada
   masa dual-write.
5. Jalankan rekonsiliasi jumlah akun/project dan uji sampel restore backup.
6. Hentikan login lama lebih dulu, tetapi jangan hapus data/kolom legacy sampai
   periode observasi selesai dan ada sign-off.

### Website ujian / student dashboard

Kode `ST-` tetap bisa dipakai pada layar lama. Login baru diarahkan ke Accounts,
kemudian sistem memakai `sub`. Penautan `sub ↔ m.siswa` ditangani modul Odoo;
record `m.siswa`, `nis`, hasil ujian, dan enrollment tidak dipindahkan.

### KodyHost

Pertahankan `ky.client` sebagai identity/billing legacy. Tambahkan mapping dari
`ky.client.id` ke `sub`; jangan mengubahnya menjadi `res.users`. Setelah link
terverifikasi, KodyHost menerima sesi lokal dari callback OIDC seperti biasa.

### KodyBlocks dan KodyBlocks Jr

Guest/IndexedDB tetap berfungsi. Setelah login, upload/copy project ke ownership
`sub` secara idempotent. Project lokal baru ditandai tersinkron setelah server
mengembalikan ID dan checksum; jangan menghapus local project otomatis.

## Logout

Logout produk menghapus sesi lokal. Bila ingin keluar dari seluruh ekosistem,
redirect juga ke `end_session_endpoint` dari discovery. Jangan mengandalkan logout
Odoo karena sesi internal Odoo memang berbeda dan tidak terkait.
