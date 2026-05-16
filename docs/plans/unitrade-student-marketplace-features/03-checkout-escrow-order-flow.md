# Checkout Escrow Order Flow Plan

Status: Draft
Priority: P1

## Tujuan

Checkout website menjadi jalur resmi yang dilindungi UniTrade. Dana buyer ditahan sampai pesanan selesai, lalu seller menerima payout manual.

## Status Saat Ini

- Cart dan checkout dasar Odoo ada.
- Xendit payment intent dan webhook menjadi flow aktif.
- Escrow ledger internal sudah dipakai untuk menahan dana seller.
- Order state khusus UniTrade dipakai untuk membedakan payment, processing, completed, dan cancelled.

## Scope MVP

- Buyer membayar order lewat website.
- Payment intent dibuat untuk order checkout.
- Setelah payment success dari webhook Xendit valid, order masuk status `processing`.
- Dana dicatat sebagai tertahan.
- Seller melihat order masuk.
- Seller klik konfirmasi barang sudah diserahkan.
- Buyer klik barang diterima.
- Order baru menjadi `completed` jika buyer dan seller sama-sama konfirmasi.
- Dana pindah ke saldo siap payout seller setelah escrow ledger menjadi `releasable`.

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
  - `xendit_reference_id`
  - `xendit_payment_request_id`
  - `payment_method_code`

- `unitrade.escrow.ledger`
  - `order_id`
  - `seller_id`
  - `buyer_id`
  - `amount_total`
  - `amount_platform_fee`
  - `amount_gateway_fee`
  - `amount_seller`
  - `state`: held, releasable, released, disputed, refunded
  - `buyer_confirmed_at`
  - `seller_confirmed_at`
  - `completed_at`
  - `released_at`
  - `payout_id`

Tambahan field di `sale.order`:

- `x_unitrade_order_state`
- `x_escrow_state`
- `x_cancel_deadline_at`
- `x_completed_at`

## Order State

- `payment_pending`
- `processing`
- `completed`
- `cancelled`
- `dispute_open`
- `refunded`

## Acceptance Criteria

- Buyer bisa membayar order lewat website.
- Webhook payment sukses membuat escrow ledger.
- Seller dashboard menampilkan order yang harus diproses.
- Dana tidak masuk payout sebelum order completed.
- Buyer bisa klik barang diterima.
- Seller bisa klik konfirmasi diserahkan.
- Order selesai hanya setelah buyer dan seller sama-sama konfirmasi.
- Jika dispute aktif, auto complete dan payout tertahan.

## Urutan Implementasi

1. Buat payment intent.
2. Integrasikan Xendit Payment Requests dari checkout website.
3. Extend webhook Xendit untuk order checkout.
4. Buat escrow ledger.
5. Tambah state order UniTrade.
6. Tambah seller order detail dan tombol konfirmasi diserahkan.
7. Tambah buyer order detail dan tombol barang diterima.
8. Test checkout, webhook, dua pihak konfirmasi, dan status pesanan.
