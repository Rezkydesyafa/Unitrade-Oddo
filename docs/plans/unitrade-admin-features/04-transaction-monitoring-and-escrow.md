# Transaction Monitoring and Escrow Plan

Status: Draft
Priority: P0

## Tujuan

Admin dapat memantau seluruh transaksi checkout website, status order, status escrow, dan riwayat status untuk validasi dan penanganan masalah.

## Scope MVP

- Daftar transaksi per order.
- Detail transaksi.
- Buyer dan seller.
- Produk dan order line.
- Nominal transaksi.
- Status pembayaran.
- Status escrow.
- Status pengiriman/serah terima.
- Riwayat status.
- Tandai transaksi bermasalah.
- Link cepat ke refund/dispute dan payout.

## Status yang Dipantau

- Payment pending.
- Paid escrow.
- Processing.
- Handoff uploaded.
- Waiting buyer confirmation.
- Completed.
- Cancelled.
- Dispute open.
- Refunded.

## Data Detail

- ID transaksi/order.
- Waktu transaksi.
- Buyer.
- Seller.
- Produk.
- Metode pembayaran.
- Nominal buyer.
- Dana platform fee.
- Dana seller.
- Status escrow.
- Bukti seller.
- Deadline auto complete.
- Dispute aktif.

## Perubahan Odoo

- Model `unitrade.payment.intent`.
- Model `unitrade.escrow.ledger`.
- Extend `sale.order` dengan state UniTrade.
- Buat tree/form/search view admin.
- Tambah smart button dari order ke escrow/dispute/payout.

## Acceptance Criteria

- Admin bisa filter transaksi per status.
- Admin bisa cari berdasarkan ID transaksi, buyer, seller, produk.
- Admin melihat status escrow per transaksi.
- Admin melihat apakah payout tertahan karena dispute.
- Admin bisa tandai transaksi bermasalah.
- Semua perubahan status tercatat.

