# Transaction Monitoring and Escrow Plan

Status: Updated after source audit
Priority: P0
Last reviewed: 2026-05-18

## Update 2026-05-18

Transaction dan escrow model sudah ada. `sale.order` sudah punya `x_payment_status`, `x_unitrade_order_state`, `x_escrow_state`, cancel deadline, cancel reason, completed time, dan payment intent relation. `unitrade.payment.intent` menyimpan provider, state, Midtrans/Xendit identifiers, raw request/response, dan intent type. `unitrade.payment.event` menyimpan webhook/event idempotency data. `unitrade.escrow.ledger` sudah menyimpan split dana per seller, platform fee, gateway fee, bukti seller/buyer, state escrow, dan payout status.

Gap admin sekarang:

- Belum ada transaction operation view yang menggabungkan order, payment intent, payment event, escrow ledger, dispute, dan payout.
- Escrow ledger belum punya search view lengkap untuk state, seller, buyer, payout status, date, dan amount.
- Belum ada flag `marked_problem` atau `admin_hold` untuk menahan transaksi tanpa langsung membuat dispute.
- Action manual `Tandai Releasable` dan `Tandai Released Manual` perlu alasan wajib, group gate, dan audit log.
- Payment/dispute menu masih tersebar di Sales/Payment root; perlu konsolidasi di menu `UniTrade`.
- Plan lama menyebut cancel window 10 menit dan auto complete 24 jam. Source saat ini memakai `unitrade.order.cancel_window_minutes = 30` dan auto confirm receipt default 48 jam. Admin settings harus menampilkan nilai aktual ini.

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

- Pakai model existing `unitrade.payment.intent`.
- Pakai model existing `unitrade.payment.event`.
- Pakai model existing `unitrade.escrow.ledger`.
- Pakai field UniTrade existing di `sale.order`.
- Tambah tree/form/search view admin yang menyatukan order, payment, escrow, dispute, dan payout.
- Tambah smart button dari order ke escrow/dispute/payout.
- Tambah transaction monitor action di `unitrade_admin` yang membuka `sale.order` dengan kolom UniTrade utama.
- Tambah field opsional `x_unitrade_problem_state`, `x_unitrade_admin_hold_reason`, `x_unitrade_admin_hold_by_id` di order atau ledger jika admin hold diperlukan.
- Tambah audit event untuk mark problem, clear problem, mark releasable, mark released, dan cancel admin.

## Acceptance Criteria

- Admin bisa filter transaksi per status.
- Admin bisa cari berdasarkan ID transaksi, buyer, seller, produk.
- Admin melihat status escrow per transaksi.
- Admin melihat apakah payout tertahan karena dispute.
- Admin bisa tandai transaksi bermasalah.
- Semua perubahan status tercatat.
