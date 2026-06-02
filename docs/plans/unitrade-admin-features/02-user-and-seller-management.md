# User and Seller Management Plan

Status: In progress - global block guard implemented
Priority: P0
Last reviewed: 2026-05-24

## Update 2026-05-24

Global account block sudah diperluas dari sekadar login/admin flag menjadi guard runtime marketplace. Helper terpusat ditambahkan di `res.users`, lalu dipakai oleh controller checkout, cart, payment handoff/confirm/cancel, refund/dispute, chat, seller dashboard/product/settings/payout, dan seller onboarding/KTM upload.

Progress task ini: sekitar 90%. Sisa kecilnya adalah polish UI notifikasi khusus blocked user di halaman profil/cart dan uji manual end-to-end dengan akun dummy yang sedang diblokir.

Progress fitur admin keseluruhan: sekitar 82%. Porsi besar yang sudah ada adalah foundation admin, audit, user/seller management, product/listing fee management, transaction monitoring, escrow controls, dan global block enforcement. Sisa utama ada di dashboard/task queue terpadu, hardening refund final, manual payout batch penuh, reports/export, system settings UI, dan admin notification center.

## Update 2026-05-18

Seller management sudah lebih maju daripada plan awal. `unitrade.seller` sudah punya status seller, OCR, approve/reject/revoke/reset, reported seller flow, store active flag, request delete flag, dan field tujuan payout. `unitrade.seller.verification` juga sudah menyimpan pending/manual review KTM dengan data OCR dan duplikasi NIM.

Gap utama sekarang bukan membuat ulang seller admin, tetapi menyatukan user risk view dan menambah global account control. Chat punya `x_unitrade_chat_blocked`, tetapi belum ada status blokir marketplace yang menghentikan transaksi, chat, upload produk, refund abuse, dan seller activity secara seragam.

Koreksi plan:

- Jangan duplikasi `unitrade.seller` dan `unitrade.seller.verification`.
- Tambah view admin user UniTrade yang membaca `res.users`, `res.partner`, seller, verification, order, chat report, dispute, dan security activity.
- Tambah field blokir global di `res.users` atau `res.partner`, misalnya `x_unitrade_account_state`, `x_unitrade_block_reason`, `x_unitrade_blocked_by_id`, `x_unitrade_blocked_at`.
- Semua action block/unblock/revoke/approve/reject harus membuat `unitrade.admin.audit.log`.
- ACL harus memakai `unitrade_seller.group_unitrade_admin`, bukan hanya `base.group_system`.

## Tujuan

Admin dapat mengelola seluruh akun pengguna, status seller, verifikasi KTM, blokir akun, dan aktivasi ulang.

## Status Saat Ini

- Seller backend view sudah ada.
- Seller verification view sudah ada.
- Approve/reject/revoke seller sudah ada sebagian.
- Halaman manajemen user UniTrade dan action block/unblock sudah ada melalui `res.users`.
- Guard global block sudah menutup aksi marketplace berisiko lintas checkout, chat, refund, dan seller.
- Belum ada satu dashboard risk terpadu yang menggabungkan user, seller status, dispute, security activity, dan SLA task.

## Scope MVP

- Daftar pengguna.
- Detail user.
- Status akun: aktif, diblokir.
- Status seller: non-seller, pending, verified, rejected, revoked.
- Data pengajuan KTM.
- Approve/reject seller verification dengan alasan.
- Blokir/aktifkan kembali akun.
- Catatan internal admin.

## Data yang Ditampilkan

- Nama.
- Email/login.
- Nomor HP.
- Tanggal daftar.
- Status OTP.
- Status akun.
- Status seller.
- Jumlah produk.
- Jumlah transaksi.
- Jumlah laporan.
- Riwayat tindakan admin.

## Action Admin

- Approve seller.
- Reject seller dengan alasan.
- Revoke seller verification.
- Block user.
- Unblock user.
- Reset ke draft verification.
- Kirim ulang email verifikasi/status.

## Perubahan Odoo

- Tambah action view user UniTrade yang memfilter user marketplace.
- Extend `res.users` dengan flag block reason jika belum ada.
- Hubungkan user detail ke seller verification dan seller record.
- Audit semua action.
- Tambah guard di controller checkout/chat/seller product/refund agar user yang diblokir global tidak bisa memakai fitur marketplace. **Selesai untuk guard utama.**
- Tambah smart button dari user ke seller, verification, orders, disputes, chat reports, security activity, dan audit log.

## Acceptance Criteria

- Admin bisa mencari user berdasarkan nama/email/nomor HP/NIM.
- Admin bisa melihat status seller dalam list user.
- Admin bisa approve/reject KTM dari detail pengajuan.
- Reject wajib alasan.
- Block user wajib alasan.
- User yang diblokir tidak bisa transaksi/chat/upload produk/refund/seller onboarding.
- Semua action masuk audit log.
