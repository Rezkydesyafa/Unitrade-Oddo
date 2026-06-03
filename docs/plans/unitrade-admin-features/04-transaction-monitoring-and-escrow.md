# Transaction Monitoring and Escrow Plan

Status: Updated after source audit
Priority: P0
Last reviewed: 2026-05-18

## Progress per 2026-05-24

- [x] Backend action `Monitoring Transaksi` di bawah menu `UniTrade > Keuangan & Dispute`.
- [x] Tree/search monitoring transaksi berbasis `sale.order` dengan filter payment status, UniTrade state, escrow state, flagged, dan tanggal.
- [x] Smart button dari order ke Payment Intent, Payment Event, Escrow Ledger, Refund/Dispute, Manual Payout, dan Audit Log.
- [x] Escrow ledger search view lengkap: state, seller, buyer, payout status, tanggal, order, amount total, dan seller amount.
- [x] Tombol form escrow untuk membuat payout manual langsung dari ledger releasable.
- [x] Aksi manual escrow `Tandai Releasable` dan `Tandai Released Manual` wajib memakai wizard alasan dan masuk audit log.
- [x] Flag/unflag transaksi bermasalah sekarang lewat helper `sale.order`, alasan wajib untuk flag, dan keduanya membuat audit log.
- [x] Helper `ensure_for_order()` ditambahkan agar sinkronisasi escrow dari perubahan status order tidak gagal diam-diam.
- [ ] Halaman operasi tunggal yang benar-benar menggabungkan semua record dalam satu layar custom masih bisa menjadi P2 jika admin membutuhkan console yang lebih padat daripada smart button/action Odoo.

## Update 2026-05-18

Transaction dan escrow model sudah ada. `sale.order` sudah punya `x_payment_status`, `x_unitrade_order_state`, `x_escrow_state`, cancel deadline, cancel reason, completed time, dan payment intent relation. `unitrade.payment.intent` menyimpan provider, state, Midtrans/Xendit identifiers, raw request/response, dan intent type. `unitrade.payment.event` menyimpan webhook/event idempotency data. `unitrade.escrow.ledger` sudah menyimpan split dana per seller, platform fee, gateway fee, bukti seller/buyer, state escrow, dan payout status.

Gap awal yang sudah ditutup/dikurangi:

- Transaction operation view sekarang tersedia sebagai action backend `Monitoring Transaksi`, dengan smart button ke payment intent, event, escrow, dispute, payout, dan audit log.
- Escrow ledger sudah punya search view untuk state, seller, buyer, payout status, tanggal, dan amount.
- Flag transaksi bermasalah memakai `x_admin_flagged` + alasan wajib + audit log. `admin_hold` terpisah belum dibuat karena belum ada kebutuhan operasional selain flag.
- Action manual `Tandai Releasable` dan `Tandai Released Manual` sudah memakai wizard alasan, group gate, dan audit log.
- Payment/dispute menu sudah dikonsolidasikan di root `UniTrade > Keuangan & Dispute`.
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
