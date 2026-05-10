# Admin Notification Center Plan

Status: Draft
Priority: P2

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

## Acceptance Criteria

- Admin melihat badge jumlah task/notifikasi.
- Klik notifikasi membuka record terkait.
- Notifikasi critical dapat muncul di dashboard.
- Admin bisa mark read.
- Event utama membuat notifikasi otomatis.

