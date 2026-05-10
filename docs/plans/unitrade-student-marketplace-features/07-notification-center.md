# Notification Center Plan

Status: Draft
Priority: P2

## Tujuan

User, seller, dan admin mendapatkan informasi status penting: listing fee, produk publish, order masuk, bukti serah/kirim, buyer confirmation, dispute, refund, dan payout.

## Status Saat Ini

- Model `unitrade.notification` ada.
- Preferensi notifikasi user ada.
- Belum ada inbox notifikasi user.
- Belum ada event notification lengkap untuk flow baru.

## Scope MVP

- Inbox notifikasi di area akun.
- Badge unread di navbar.
- Mark read.
- Event notification untuk flow listing fee, order, dispute, payout.
- Email notification mengikuti preferensi user.

## Event Notifikasi

Seller:

- Fee upload menunggu pembayaran.
- Fee upload berhasil.
- Produk publish.
- Order checkout masuk.
- Buyer membatalkan pesanan.
- Buyer mengajukan banding/refund.
- Dana siap payout.
- Payout sudah dibayar.

Buyer:

- Pembayaran berhasil.
- Seller upload bukti serah/kirim.
- Reminder klik pesanan selesai.
- Order auto complete.
- Cancel/refund diterima atau ditolak.
- CS meminta bukti tambahan.

Admin/CS:

- Seller verification manual review.
- Dispute/refund baru.
- Payout siap dibayar.

## Perubahan Odoo

- Extend `unitrade.notification` dengan:
  - `action_url`
  - `priority`
  - `payload_json`
  - `read_at`
- Controller:
  - `GET /my/notifications`
  - `POST /unitrade/notifications/read`
  - `POST /unitrade/notifications/read_all`
- Template:
  - inbox notification
  - navbar badge

## Acceptance Criteria

- User melihat daftar notifikasi.
- Badge unread muncul di navbar.
- Klik notifikasi membuka halaman terkait.
- User bisa mark read.
- Notifikasi mengikuti preferensi user untuk email.
- Event utama checkout/refund/payout membuat notifikasi.

## Urutan Implementasi

1. Extend model notification.
2. Buat helper create notification.
3. Buat inbox page.
4. Tambah navbar badge.
5. Hubungkan event listing fee dan checkout.
6. Hubungkan event dispute/refund.
7. Hubungkan event payout.

