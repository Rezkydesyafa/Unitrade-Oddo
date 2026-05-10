# UniTrade Admin Feature Brainstorm and Implementation Plan

Tanggal: 2026-05-10
Status: Draft brainstorming admin features
Target platform: Odoo 17 backend, custom UniTrade admin modules

## 1. Tujuan Admin

Admin UniTrade dibutuhkan untuk menjaga marketplace tetap aman, tertib, dan bisa diaudit. Karena UniTrade memakai konsep katalog mahasiswa, fee upload produk, checkout website dengan escrow, refund berbasis bukti, dan payout manual, admin harus punya kontrol penuh atas empat area:

- Trust and safety: verifikasi seller, blokir user, moderasi laporan.
- Marketplace operations: produk, transaksi, escrow, refund, payout.
- Financial control: fee upload produk, GMV, dana tertahan, dana siap payout.
- Reporting and governance: laporan, konfigurasi sistem, audit log, kebijakan.

## 2. Ringkasan Fitur dari Gambar

List fitur awal dari gambar sudah relevan dan menjadi dasar plan:

- Dashboard Admin
  - Statistik pengguna.
  - Statistik seller terverifikasi.
  - Pending verifikasi KTM.
  - Statistik produk.
  - Statistik transaksi berdasarkan status.
  - GMV total dan grafik GMV 7 hari terakhir.
  - Daftar tugas admin.
- Manajemen Pengguna
  - Daftar user.
  - Detail user.
  - Status aktif/diblokir.
  - Status seller verified/unverified.
  - Approve/reject verifikasi seller.
  - Blokir dan aktifkan akun.
- Reports dan Laporan
  - Laporan transaksi.
  - Laporan pengguna.
  - Laporan produk.
  - Laporan refund.
  - Filter tanggal.
  - Export PDF/Excel.
- Monitoring Transaksi
  - Daftar transaksi per order.
  - Detail buyer, seller, produk, nominal, status.
  - Status escrow.
  - Riwayat status.
  - Pencarian dan filter.
  - Tandai transaksi bermasalah.
- Pengaturan Sistem
  - Konfigurasi utama operasional platform.

## 3. Fitur Admin yang Dibutuhkan

| Prioritas | Fitur | Kenapa perlu |
| --- | --- | --- |
| P0 | Admin dashboard dan task queue | Admin butuh ringkasan kondisi marketplace dan pekerjaan yang harus diproses |
| P0 | Manajemen user dan seller | Wajib untuk verifikasi KTM, blokir akun, dan kontrol seller |
| P0 | Product dan listing fee management | Produk tidak boleh publish sebelum fee upload lunas |
| P0 | Transaction monitoring dan escrow | Admin perlu melihat status dana, order, dan risiko transaksi |
| P0 | Refund dan dispute management | Konsep refund wajib video unboxing membutuhkan CS/admin review |
| P0 | Manual payout management | Payout seller diputuskan manual pada MVP |
| P1 | Reports dan export | Dibutuhkan untuk evaluasi, monitoring GMV, refund, user, produk |
| P1 | System settings | Tarif fee, deadline cancel/refund, payout, dan policy harus configurable |
| P1 | Moderation dan audit log | Semua aksi admin harus terlacak |
| P2 | Admin notification center | Admin perlu notifikasi pending KTM, refund, payout, overdue order |

## 4. Status Saat Ini dari Project

Yang sudah ada sebagian:

- Backend menu UniTrade.
- Seller list, seller pending, seller reported.
- Seller verification views.
- Product marketplace backend view.
- Payment status field di sale order.
- Delivery backend view.
- Review backend view.
- Chat report moderation.

Yang belum terlihat lengkap:

- Dashboard admin terpadu.
- Task queue admin.
- Laporan GMV dan grafik.
- Export laporan.
- Fee upload product management.
- Escrow ledger management.
- Manual payout management.
- Refund/dispute case management.
- System settings untuk tarif fee, SLA, policy, dan payout.
- Audit log yang menyimpan aksi admin lintas modul.

## 5. Dokumentasi Per Fitur

Detail plan per fitur disimpan di:

`docs/plans/unitrade-admin-features/`

Daftar dokumen:

- [Admin Feature Gap and Roadmap](unitrade-admin-features/00-admin-feature-gap-and-roadmap.md)
- [Admin Dashboard and Task Queue](unitrade-admin-features/01-admin-dashboard-and-task-queue.md)
- [User and Seller Management](unitrade-admin-features/02-user-and-seller-management.md)
- [Product and Listing Fee Management](unitrade-admin-features/03-product-and-listing-fee-management.md)
- [Transaction Monitoring and Escrow](unitrade-admin-features/04-transaction-monitoring-and-escrow.md)
- [Refund Dispute Management](unitrade-admin-features/05-refund-dispute-management.md)
- [Manual Payout Management](unitrade-admin-features/06-manual-payout-management.md)
- [Reports and Export](unitrade-admin-features/07-reports-and-export.md)
- [System Settings](unitrade-admin-features/08-system-settings.md)
- [Moderation and Audit Log](unitrade-admin-features/09-moderation-and-audit-log.md)
- [Admin Notification Center](unitrade-admin-features/10-admin-notification-center.md)

## 6. Roadmap Admin

### Fase 1: Admin Control Dasar

- Admin dashboard.
- Task queue.
- User/seller management.
- Product/listing fee management.

### Fase 2: Transaksi dan Risiko

- Transaction monitoring.
- Escrow ledger.
- Refund/dispute management.
- Manual payout management.

### Fase 3: Governance

- Reports/export.
- System settings.
- Audit log.
- Admin notification center.

## 7. Prinsip Implementasi Odoo

- Gunakan backend Odoo untuk admin utama, bukan website public.
- Buat group akses khusus `unitrade_seller.group_unitrade_admin` atau role admin tambahan jika perlu.
- Jangan simpan credential payment/payout hardcoded. Gunakan `ir.config_parameter`.
- Semua tindakan penting admin harus membuat audit log.
- Semua list operasional harus punya search/filter: status, tanggal, user, seller, amount.
- Semua amount tampil dalam format Rupiah tanpa desimal.

## 8. Acceptance Criteria Global

- Admin dapat melihat ringkasan marketplace dalam satu dashboard.
- Admin dapat memproses semua pending task dari satu tempat.
- Admin dapat mencari user, seller, produk, transaksi, refund, dan payout.
- Admin dapat approve/reject seller verification dengan alasan.
- Admin dapat melihat fee upload produk dan status pembayarannya.
- Admin dapat melihat escrow dan status dana per transaksi.
- Admin dapat review refund/dispute beserta bukti.
- Admin dapat memproses payout manual dan upload bukti transfer.
- Admin dapat export laporan periode tertentu.
- Semua aksi kritis admin tercatat di audit log.
