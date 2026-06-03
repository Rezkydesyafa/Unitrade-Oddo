# UniTrade Admin Feature Brainstorm and Implementation Plan

Tanggal: 2026-05-10
Last reviewed: 2026-05-18
Status: Updated after source audit
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
| P0 | Admin foundation dan security convergence | Role admin UniTrade harus konsisten lintas modul sebelum dashboard/task/report dibangun |
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

Audit source 2026-05-18 menunjukkan plan lama perlu dikoreksi. Beberapa fitur yang dulu ditulis sebagai gap sekarang sudah ada sebagian, tetapi belum menjadi admin operation center yang konsisten.

Yang sudah ada sebagian:

- Backend root menu `UniTrade` dari `unitrade_seller` dengan sub menu penjual, produk, review, delivery, dan chat moderation.
- Group `unitrade_seller.group_unitrade_admin` sudah ada, tetapi belum dipakai konsisten oleh semua modul admin.
- Seller management sudah punya list, pending, reported, approve, reject, revoke, reset draft, OCR result, dan field tujuan payout di `unitrade.seller`.
- Seller verification sudah punya model terpisah `unitrade.seller.verification` dengan state `draft`, `pending`, `manual_review`, `approved`, `rejected`.
- Product marketplace backend sudah ada di `unitrade_product_ext`, termasuk field seller, stok, lokasi, `x_listing_fee`, `x_listing_expires_at`, publish/unpublish.
- Listing fee flow sudah ada sebagian melalui `unitrade.payment.intent` dengan `intent_type = listing_fee` dan publish produk setelah intent paid.
- Payment monitoring sudah lebih lengkap: `unitrade.payment.intent`, `unitrade.payment.event`, field payment pada `sale.order`, Midtrans aktif, Xendit legacy masih ada.
- Escrow ledger sudah ada di `unitrade.escrow.ledger` dengan state `held`, `releasable`, `released`, `disputed`, `refunded`, `cancelled`, bukti serah terima, dan field payout.
- Refund/dispute sudah ada di `unitrade_dispute` dengan model `unitrade.dispute`, `unitrade.dispute.evidence`, backend view, buyer form, seller response, dan hold escrow.
- Notification model sudah ada di `unitrade.notification`, tetapi masih user-centric dan belum menjadi admin notification center.
- Account security activity sudah ada di `unitrade.security.activity`, tetapi belum menjadi audit log admin lintas modul.

Yang masih perlu ditambahkan atau dikoreksi:

- Modul orkestrasi `unitrade_admin` sebaiknya dibuat tipis untuk dashboard, task queue, audit log, settings, report, dan menu consolidation. Business logic payment/seller/dispute tetap di modul yang sudah ada.
- ACL dan menu perlu diseragamkan: payment/dispute masih banyak memakai `base.group_system` atau `sales_team.group_sale_manager`, sedangkan admin UniTrade seharusnya memakai `unitrade_seller.group_unitrade_admin`.
- Public model action kritis perlu gatekeeping eksplisit dengan `has_group()` atau `check_access_rights()`, terutama approve/reject refund, release payout, revoke seller, waive fee, dan change settings.
- Product listing belum punya status eksplisit seperti `fee_pending`, `fee_paid`, `waived`, `rejected`; sekarang status masih disimpulkan dari `sale_ok`, `website_published`, payment intent, dan expiry.
- Fee upload saat ini memakai `ir.config_parameter` sederhana (`threshold`, `low_amount`, `high_amount`, `posting_admin_fee`), bukan tier persentase seperti plan lama. Admin settings harus mengikuti implementasi sekarang atau migration tier harus direncanakan eksplisit.
- Default runtime sekarang berbeda dari asumsi lama: cancel window `unitrade.order.cancel_window_minutes` = 30 menit, auto confirm receipt `unitrade.escrow.auto_confirm_receipt_hours` default 48 jam, upload refund max `unitrade.refund.max_upload_mb` = 25 MB.
- Manual payout belum punya model batch dengan bukti transfer. `unitrade.escrow.ledger` punya `payout_reference`, `payout_status`, dan manual mark released, tetapi belum cukup untuk audit payout manual MVP.
- Refund/dispute sudah ada, tetapi admin approval masih perlu validasi minimum evidence, catatan keputusan wajib, SLA deadline, dan audit event.
- Dashboard terpadu, task queue, reports/export, settings UI, audit log admin, dan admin notification center belum ada.

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

### Fase 0: Admin Foundation dan Security Convergence

- Buat modul `unitrade_admin` sebagai orkestrasi admin.
- Satukan menu admin di bawah `UniTrade`.
- Terapkan `unitrade_seller.group_unitrade_admin` pada action/menu/model admin lintas modul.
- Tambah helper audit log untuk action kritis.
- Gate public/admin actions yang bisa dipanggil RPC.

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
- Gunakan existing group `unitrade_seller.group_unitrade_admin` sebagai role admin utama, lalu tambahkan subgroup hanya jika ada kebutuhan CS/finance yang jelas.
- Hindari memindahkan logic yang sudah stabil dari `unitrade_seller`, `unitrade_payment`, dan `unitrade_dispute`; `unitrade_admin` cukup mengorkestrasi dashboard, task, report, settings, dan audit.
- Jangan simpan credential payment/payout hardcoded. Gunakan `ir.config_parameter`.
- Semua tindakan penting admin harus membuat audit log.
- Semua list operasional harus punya search/filter: status, tanggal, user, seller, amount.
- Semua amount tampil dalam format Rupiah tanpa desimal.
- Public method Odoo yang berdampak finansial/trust harus melakukan pengecekan group di method, bukan hanya mengandalkan tombol view.

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
- ACL dan menu admin konsisten memakai role admin UniTrade.
- Admin dapat mengubah setting operasional dari UI tanpa edit XML/data file.
