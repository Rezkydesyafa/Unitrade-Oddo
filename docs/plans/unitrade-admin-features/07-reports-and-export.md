# Reports and Export Plan

Status: Draft
Priority: P1

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

## Acceptance Criteria

- Admin bisa memilih periode.
- Admin bisa melihat ringkasan sebelum export.
- Export menampilkan angka Rupiah tanpa desimal.
- Export transaksi bisa difilter per status.
- Export refund memuat status penyelesaian.

