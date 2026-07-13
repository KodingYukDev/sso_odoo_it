# Security Audit Log

Audit trail tersedia di **KodingYuk Accounts → Audit Logs**. Record bersifat
append-only: pengguna Odoo, termasuk Accounts Manager, hanya dapat membaca dan
tidak dapat mengubah atau menghapus record melalui ORM/UI.

## Event yang dicatat

- Registrasi berhasil/gagal.
- Login berhasil/gagal dan alasan aman seperti credentials atau email belum aktif.
- Permintaan dan penyelesaian verifikasi email.
- Permintaan, kegagalan, dan penyelesaian reset password.
- Claim siswa serta perubahan status link siswa oleh admin.
- Consent yang diberikan/dicabut.
- Perubahan status akun.
- Authorization OIDC berhasil/gagal.
- Token OIDC diterbitkan/gagal dan logout berhasil.
- Purge otomatis berdasarkan retention policy.

## Data yang disimpan

- Timestamp, event, outcome, akun/subject UUID, client ID, request ID, dan source.
- Identifier yang sudah dimasking, misalnya `a***@domain.id`; bukan email penuh.
- IP dan user-agent, hanya terlihat oleh **Accounts Manager**.
- Metadata aman dan terbatas seperti reason code, status claim, atau purpose consent.
- Internal Odoo user yang melakukan perubahan manual.

Audit tidak menyimpan password, password hash, kode siswa `ST-`, authorization
code, access/refresh token, token verifikasi email, atau token reset password.

## Retention

Default retention adalah 365 hari dan dapat diubah pada **KodingYuk Accounts →
Settings → Security Audit** dengan minimum 30 hari. Scheduled action berjalan
setiap hari dan menghapus record di luar retention melalui jalur terkontrol, lalu
membuat event ringkasan `audit.retention_purge`.

Sesuaikan retention dengan Kebijakan Privasi dan kebutuhan legal. Karena IP dan
user-agent merupakan data audit keamanan, akses grup Accounts Manager harus
dibatasi dan export log harus diperlakukan sebagai data sensitif.

## Upgrade instalasi existing

Sesudah source addon dan web diperbarui, upgrade modul Odoo lalu restart web:

```bash
odoo-bin -d NAMA_DATABASE -u sso_odoo_it --stop-after-init
```

Upgrade menambah tabel audit, menu, access rule, dan scheduled action. Tidak ada
record akun atau siswa yang dihapus.
