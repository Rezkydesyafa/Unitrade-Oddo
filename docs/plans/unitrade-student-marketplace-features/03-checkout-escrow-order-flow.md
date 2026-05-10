# Checkout Escrow Order Flow Plan

Status: Draft
Priority: P1

## Tujuan

Checkout website menjadi jalur resmi yang dilindungi UniTrade. Dana buyer ditahan sampai pesanan selesai, lalu seller menerima payout manual.

## Status Saat Ini

- Cart dan checkout dasar Odoo ada.
- Midtrans model dan webhook ada sebagian.
- Belum ada frontend Snap/checkout payment flow penuh.
- Belum ada escrow ledger.
- Belum ada order state khusus UniTrade.

## Scope MVP

- Buyer membayar order lewat website.
- Payment intent dibuat untuk order checkout.
- Setelah payment success, order masuk status `paid_escrow`.
- Dana dicatat sebagai tertahan.
- Seller melihat order masuk.
- Seller upload bukti serah/kirim.
- Buyer klik pesanan selesai.
- Jika buyer tidak klik selesai dalam 24 jam, cron auto complete.
- Dana pindah ke saldo siap payout seller.

## Data Model

Model baru:

- `unitrade.payment.intent`
  - `name`
  - `intent_type`: listing_fee, order_checkout
  - `state`: draft, pending, paid, failed, expired, refunded
  - `amount`
  - `currency_id`
  - `sale_order_id`
  - `product_template_id`
  - `seller_id`
  - `midtrans_transaction_id`
  - `midtrans_snap_token`

- `unitrade.escrow.ledger`
  - `order_id`
  - `seller_id`
  - `buyer_id`
  - `amount_total`
  - `amount_platform_fee`
  - `amount_seller`
  - `state`: held, releasable, released, disputed, refunded
  - `released_at`
  - `payout_id`

Tambahan field di `sale.order`:

- `x_unitrade_order_state`
- `x_escrow_state`
- `x_buyer_confirmed_at`
- `x_auto_complete_at`
- `x_seller_handoff_at`

## Order State

- `payment_pending`
- `paid_escrow`
- `processing`
- `handoff_uploaded`
- `buyer_confirmation_pending`
- `completed`
- `cancelled`
- `dispute_open`
- `refunded`

## Acceptance Criteria

- Buyer bisa membayar order lewat website.
- Webhook payment sukses membuat escrow ledger.
- Seller dashboard menampilkan order yang harus diproses.
- Dana tidak masuk payout sebelum order completed.
- Buyer bisa klik selesai setelah seller upload bukti.
- Cron menyelesaikan order otomatis 24 jam setelah bukti seller jika tidak ada dispute.
- Jika dispute aktif, auto complete dan payout tertahan.

## Urutan Implementasi

1. Buat payment intent.
2. Integrasikan Midtrans Snap dari checkout website.
3. Extend webhook Midtrans untuk order checkout.
4. Buat escrow ledger.
5. Tambah state order UniTrade.
6. Tambah seller order detail.
7. Tambah buyer order detail dan tombol selesai.
8. Buat cron auto complete.
9. Test checkout, webhook, auto complete, dan status pesanan.

