# Admin Dashboard and Task Queue Plan

Status: Updated after source audit
Priority: P0
Last reviewed: 2026-05-18

## Update 2026-05-18

Project sekarang sudah punya banyak sumber data yang dulu belum ada: `unitrade.seller`, `unitrade.seller.verification`, `product.template` marketplace, `unitrade.payment.intent`, `unitrade.payment.event`, `unitrade.escrow.ledger`, `unitrade.dispute`, `unitrade.chat.report`, `unitrade.delivery`, dan `unitrade.review`. Jadi dashboard tidak perlu membuat ulang model operasional. Yang perlu dibuat adalah modul orkestrasi `unitrade_admin` untuk membaca metrik dan membuka record sumber.

## Progress per 2026-05-24

- [x] Module `unitrade_admin` dibuat (controller + model `unitrade.admin.stats`)
- [x] Halaman dashboard `/unitrade/admin` dengan stat cards, GMV chart 7 hari, task summary
- [x] Halaman Manajemen Pengguna `/unitrade/admin/users` (filter, block/unblock, approve/reject seller)
- [x] Halaman Monitoring Transaksi `/unitrade/admin/transactions` (filter status, flag/unflag)
- [x] Halaman Laporan `/unitrade/admin/reports` + CSV export
- [x] Halaman Pengaturan Sistem `/unitrade/admin/settings`
- [x] Halaman **Antrian Tugas terpadu** `/unitrade/admin/tasks` (NEW): KTM review, reported sellers, dispute aktif, payout siap, escrow stuck, listing fee pending, order overdue, flagged orders. Filter urgent/warning. Sumber: `get_task_queue()`.
- [x] Notification dropdown topbar dengan live derived dari domain
- [x] ACL via `unitrade_seller.group_unitrade_admin`
- [ ] Snapshot harian (`unitrade.admin.dashboard.snapshot`) — ditunda sampai query mulai berat
- [ ] Backend Odoo dashboard widget (saat ini hanya custom dashboard `/unitrade/admin`)

Task queue harus dibangun dari domain lintas model, bukan task manual saja:

| Queue                       | Sumber data                                       | Domain awal                                                                     |
| --------------------------- | ------------------------------------------------- | ------------------------------------------------------------------------------- |
| KTM pending/manual review   | `unitrade.seller.verification`, `unitrade.seller` | state/status pending atau manual review                                         |
| Listing fee pending/expired | `unitrade.payment.intent`, `product.template`     | `intent_type = listing_fee`, state pending/failed/expired, produk belum publish |
| Order perlu diproses        | `sale.order`, `unitrade.escrow.ledger`            | paid/processing, seller belum confirm, buyer belum confirm, deadline lewat      |
| Refund aktif                | `unitrade.dispute`                                | submitted/under_review/need_buyer_evidence/need_seller_response                 |
| Payout siap                 | `unitrade.escrow.ledger`                          | state releasable, payout belum succeeded, tidak dispute                         |
| Moderasi                    | `unitrade.chat.report`, `unitrade.seller`         | report submitted/reported/under_review                                          |

Koreksi acceptance: dashboard harus memakai group `unitrade_seller.group_unitrade_admin`, dan semua kartu harus membuka action existing dengan context/filter, bukan halaman statis.

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

Module yang disarankan: `unitrade_admin` sebagai layer orkestrasi.

Model opsional:

- `unitrade.admin.dashboard.snapshot` untuk cache metrik harian jika query langsung mulai berat.
- `unitrade.admin.task` untuk materialized task hanya jika domain lintas model tidak cukup.

Service/helper:

- `unitrade.admin.metric.service` atau model method internal untuk hitung metrik.
- Helper action builder untuk membuka source record dengan filter yang sama seperti kartu dashboard.

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
