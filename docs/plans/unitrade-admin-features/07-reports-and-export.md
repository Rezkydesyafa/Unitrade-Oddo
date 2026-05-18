# Reports and Export Plan

Status: Updated after source audit
Priority: P1
Last reviewed: 2026-05-18

## Update 2026-05-18

Data sumber laporan sudah lebih lengkap daripada saat plan awal dibuat. Reports bisa membaca `sale.order`, `unitrade.payment.intent`, `unitrade.payment.event`, `unitrade.escrow.ledger`, `unitrade.dispute`, `unitrade.seller`, `unitrade.seller.verification`, `product.template`, `unitrade.review`, `unitrade.chat.report`, dan nanti `unitrade.seller.payout`.

Koreksi scope:

- Export laporan harus memakai model existing, bukan membuat tabel transaksi baru.
- Untuk MVP, buat wizard ringkasan periode dan CSV/XLSX transaksi/refund/payout. PDF ringkasan bisa P2 jika belum ada format final.
- Report GMV harus membedakan order checkout website yang paid dari listing fee revenue.
- Escrow report harus memisahkan `held`, `releasable`, `released`, `disputed`, `refunded`, dan `cancelled`.
- Refund report harus membaca SLA once field deadline ditambahkan.
- Semua export harus mencantumkan timestamp export, admin yang export, filter yang dipakai, dan masuk audit log.

## Tujuan

Admin dapat membuat laporan monitoring dan evaluasi platform berdasarkan periode tertentu.

## Jenis Laporan

Laporan transaksi:

- Total transaksi per periode.
- Total GMV.
- Jumlah transaksi per status.
- Escrow held/released/refunded.
- Payment failed/expired.

Laporan pengguna:

- User baru.
- User aktif.
- Seller terverifikasi.
- Pending seller.
- User diblokir.

Laporan produk:

- Total produk.
- Produk aktif.
- Produk pending fee.
- Produk rejected.
- Produk per kategori.

Laporan refund:

- Jumlah refund diajukan.
- Refund approved/rejected.
- Rata-rata waktu penyelesaian.
- Nilai refund.

Laporan payout:

- Dana siap cair.
- Dana sudah payout.
- Dana tertahan dispute.
- Payout per seller.

## Filter

- Tanggal mulai dan akhir.
- Status.
- Seller.
- Buyer.
- Kategori produk.
- Metode pembayaran.

## Export

- Excel/XLSX.
- PDF ringkasan.
- CSV untuk data mentah jika dibutuhkan.

## Perubahan Odoo

- Wizard laporan.
- Report model atau transient model.
- XLSX export helper.
- PDF QWeb report jika diperlukan.
- Tambah audit event untuk export report.
- Tambah saved filters untuk GMV, escrow, refund, payout, listing fee, seller verification, dan moderation.

## Acceptance Criteria

- Admin bisa memilih periode.
- Admin bisa melihat ringkasan sebelum export.
- Export menampilkan angka Rupiah tanpa desimal.
- Export transaksi bisa difilter per status.
- Export refund memuat status penyelesaian.
