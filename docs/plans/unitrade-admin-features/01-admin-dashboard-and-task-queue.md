# Admin Dashboard and Task Queue Plan

Status: Draft
Priority: P0

## Tujuan

Admin punya satu halaman ringkasan untuk melihat kondisi UniTrade dan pekerjaan yang harus diproses.

## Konten Dashboard

Statistik pengguna:

- Total pengguna terdaftar.
- Total seller terverifikasi.
- Jumlah pengajuan verifikasi KTM pending/manual review.
- Jumlah user diblokir.

Statistik produk:

- Total produk aktif.
- Produk pending fee.
- Produk pending review.
- Produk diarsipkan/ditolak.

Statistik transaksi:

- Total transaksi.
- Diproses.
- Menunggu konfirmasi buyer.
- Selesai.
- Refund/dispute.
- Dibatalkan.

GMV:

- Total GMV.
- GMV 7 hari terakhir.
- Grafik GMV harian.
- Listing fee revenue.

Task queue:

- Pengajuan KTM belum diproses.
- Produk pending fee/review.
- Transaksi menunggu konfirmasi melewati batas waktu.
- Refund/dispute belum ditinjau.
- Payout belum diproses.
- Laporan chat/seller belum selesai.

## Perubahan Odoo

Module yang disarankan: `unitrade_admin`.

Model opsional:

- `unitrade.admin.dashboard.snapshot` untuk cache metrik harian.
- `unitrade.admin.task` untuk menyatukan task lintas modul.

View:

- `unitrade_admin_dashboard_action`
- menu `UniTrade > Dashboard Admin`

## Acceptance Criteria

- Admin melihat semua metrik utama dalam satu halaman.
- Admin bisa klik kartu task untuk membuka list terkait.
- Dashboard menampilkan GMV 7 hari terakhir.
- Dashboard menampilkan pending task count.
- Dashboard hanya bisa diakses admin UniTrade.

## Urutan Implementasi

1. Buat module `unitrade_admin`.
2. Buat controller/model dashboard atau client action.
3. Query metrik dari user, seller, product, sale order, dispute, payout.
4. Buat task queue sederhana dari domain lintas model.
5. Tambah chart GMV 7 hari.
6. Tambah menu admin dashboard.

