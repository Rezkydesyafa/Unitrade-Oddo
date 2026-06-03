# Admin Notification Center Plan

Status: MVP implemented
Priority: P2
Last reviewed: 2026-05-24

## Progress per 2026-05-24

- [x] Extend `unitrade.notification` dengan `audience`, `priority`, target model/id/url, `action_xmlid`, `dedupe_key`, `read_at`, dan `read_by_id`.
- [x] Helper `create_admin_notification()` dengan dedupe supaya task yang sama tidak membuat spam.
- [x] Admin topbar memakai notifikasi persistent dari database, bukan localStorage.
- [x] API mark read dan mark all read.
- [x] Halaman inbox `/unitrade/admin/notifications` dengan filter unread/read dan priority.
- [x] Backend action/menu `Notifikasi Admin` untuk model `unitrade.notification`.
- [x] Sinkronisasi MVP dari `get_task_queue()`: KTM/manual review, reported seller, refund/dispute, payout, escrow stuck, listing fee pending, order overdue, flagged order.
- [ ] Event hook langsung dari setiap aksi/domain source saat record dibuat/berubah. Saat ini MVP memakai sync dari task queue agar tetap konsisten dengan source of truth.
- [ ] Dedupe lifecycle lebih halus untuk resolved task, misalnya badge "resolved" alih-alih hanya auto-read.
- [ ] Assignment/ownership per admin/CS jika nanti workflow butuh pembagian kerja.

## Update 2026-05-18

`unitrade.notification` sudah ada, tetapi modelnya masih user-centric: `user_id`, title, message, type, read flag, reference model/id. Ini sekarang diperluas untuk admin notification center tanpa membuat model baru.

Koreksi plan:

- Untuk MVP, extend `unitrade.notification` dengan `audience`, `priority`, `target_model`, `target_id`, `action_xmlid` atau computed backend URL, dan `dedupe_key`.
- Jika admin notification butuh assignment/ownership, baru buat `unitrade.admin.notification`.
- Notification center harus sinkron dengan task queue. Notification memberi event baru; task queue tetap dihitung dari source of truth.
- Event critical seperti refund submitted, payout ready, seller manual review, listing payment failed, chat report submitted, dan order overdue harus muncul di dashboard.

## Tujuan

Admin mendapat notifikasi untuk pekerjaan penting agar tidak melewatkan KTM pending, refund, payout, atau transaksi yang melewati batas waktu.

## Event Notifikasi Admin

- Seller verification masuk pending/manual review.
- Produk baru menunggu fee/review.
- Payment listing fee gagal/expired.
- Order checkout berhasil dibayar.
- Order menunggu konfirmasi buyer melewati batas.
- Refund/dispute baru.
- Buyer mengirim bukti tambahan.
- Seller mengirim respons dispute.
- Payout siap diproses.
- Laporan chat/seller baru.

## UI

- Badge admin notification di backend menu atau dashboard.
- Inbox admin notification.
- Filter unread/read.
- Link langsung ke record terkait.
- Mark read dan mark all read.

## Perubahan Odoo

- Extend `unitrade.notification` atau buat `unitrade.admin.notification`.
- Tambah `action_url`, `target_model`, `target_id`, `priority`.
- Helper service untuk create notification.
- Integrasi ke dashboard task queue.
- Tambah dedupe agar cron/refresh tidak membuat notifikasi ganda untuk task yang sama.
- Tambah access untuk `unitrade_seller.group_unitrade_admin`.

## Acceptance Criteria

- Admin melihat badge jumlah task/notifikasi.
- Klik notifikasi membuka record terkait.
- Notifikasi critical dapat muncul di dashboard.
- Admin bisa mark read.
- Event utama membuat notifikasi otomatis.
