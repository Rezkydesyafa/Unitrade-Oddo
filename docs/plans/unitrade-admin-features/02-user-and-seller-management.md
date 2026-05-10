# User and Seller Management Plan

Status: Draft
Priority: P0

## Tujuan

Admin dapat mengelola seluruh akun pengguna, status seller, verifikasi KTM, blokir akun, dan aktivasi ulang.

## Status Saat Ini

- Seller backend view sudah ada.
- Seller verification view sudah ada.
- Approve/reject/revoke seller sudah ada sebagian.
- Belum ada satu halaman manajemen user yang menggabungkan user, seller status, dan risk status.

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

## Acceptance Criteria

- Admin bisa mencari user berdasarkan nama/email/nomor HP/NIM.
- Admin bisa melihat status seller dalam list user.
- Admin bisa approve/reject KTM dari detail pengajuan.
- Reject wajib alasan.
- Block user wajib alasan.
- User yang diblokir tidak bisa transaksi/chat/upload produk.
- Semua action masuk audit log.

