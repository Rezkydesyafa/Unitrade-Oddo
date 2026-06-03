# UniTrade Admin Feature Plans

Folder ini berisi rencana fitur admin untuk konsep UniTrade sebagai katalog mahasiswa dan marketplace checkout terproteksi.

Last reviewed: 2026-05-18

## Catatan Update 2026-05-18

Source audit terbaru menunjukkan beberapa fitur admin sudah berkembang sejak plan awal dibuat:

- `unitrade_payment` sudah punya payment intent, payment event, escrow ledger, Midtrans flow, dan Xendit legacy field.
- `unitrade_dispute` sudah punya model refund/dispute, evidence, backend view, buyer refund form, dan seller response.
- `unitrade_seller` sudah punya seller verification, reported seller review, revoke verification, dan field tujuan payout.
- `unitrade_notification` sudah ada, tetapi masih untuk user notification, belum admin notification center.
- `unitrade.security.activity` sudah ada untuk aktivitas akun, tetapi belum menggantikan audit log admin lintas modul.

Karena itu, dokumen di folder ini sekarang harus dibaca sebagai rencana konsolidasi admin: gunakan model yang sudah ada, tambahkan modul orkestrasi `unitrade_admin`, dan koreksi security/ACL sebelum membangun dashboard, task queue, report, settings, payout manual, dan audit log.

## Urutan Baca

1. [Feature Gap and Roadmap](00-admin-feature-gap-and-roadmap.md)
2. [Admin Dashboard and Task Queue](01-admin-dashboard-and-task-queue.md)
3. [User and Seller Management](02-user-and-seller-management.md)
4. [Product and Listing Fee Management](03-product-and-listing-fee-management.md)
5. [Transaction Monitoring and Escrow](04-transaction-monitoring-and-escrow.md)
6. [Refund Dispute Management](05-refund-dispute-management.md)
7. [Manual Payout Management](06-manual-payout-management.md)
8. [Reports and Export](07-reports-and-export.md)
9. [System Settings](08-system-settings.md)
10. [Moderation and Audit Log](09-moderation-and-audit-log.md)
11. [Admin Notification Center](10-admin-notification-center.md)

## Roadmap Singkat

| Fase | Fokus | Dokumen |
| --- | --- | --- |
| 0 | Admin foundation, menu consolidation, ACL, audit helper | 00, 09 |
| 1 | Dashboard, task queue, user/seller, produk/fee | 01, 02, 03 |
| 2 | Transaksi, escrow, refund, payout manual | 04, 05, 06 |
| 3 | Laporan, konfigurasi, audit, notifikasi admin | 07, 08, 09, 10 |
