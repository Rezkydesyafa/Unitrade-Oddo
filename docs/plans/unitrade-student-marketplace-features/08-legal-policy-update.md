# Legal Policy Update Plan

Status: Draft
Priority: P2

## Tujuan

Halaman FAQ/syarat UniTrade harus menjelaskan batas perlindungan katalog, fee upload produk, checkout escrow, cancel 10 menit, refund, video unboxing, video packing, dan link Google Drive.

## Status Saat Ini

- Halaman legal/FAQ sudah ada.
- Beberapa copy menyebut pembayaran dan dana ditahan.
- Belum ada kebijakan rinci untuk transaksi luar website, fee upload, cancel, dan refund evidence.

## Scope MVP

Tambahkan section legal:

- Mode katalog dan transaksi luar website.
- Proteksi checkout website.
- Biaya upload produk untuk seller.
- Pembatalan pesanan.
- Banding setelah 10 menit.
- Refund dengan video unboxing.
- Pengembalian barang dengan video packing dan Google Drive.
- Payout seller manual.

## Copy Policy Ringkas

### Transaksi Luar Website

Transaksi yang diselesaikan di luar website UniTrade tidak dilindungi escrow, refund, atau proses banding UniTrade. UniTrade hanya menyediakan katalog, profil seller, dan chat sebagai sarana komunikasi.

### Checkout Website

Transaksi yang checkout dan dibayar melalui website UniTrade mendapat perlindungan dana tertahan sampai pesanan selesai atau sampai proses banding/refund selesai.

### Fee Upload Produk

Seller wajib membayar biaya upload produk sebelum produk dipublikasikan. Besaran biaya dihitung berdasarkan harga produk dan dapat berubah sesuai kebijakan platform.

### Pembatalan

Buyer dapat membatalkan pesanan secara langsung maksimal 10 menit setelah checkout, selama seller belum mengunggah bukti serah/kirim. Setelah batas tersebut, pembatalan wajib melalui banding.

### Refund

Refund hanya berlaku untuk transaksi checkout website. Buyer wajib menyertakan video unboxing tanpa potongan. Jika barang harus dikembalikan, buyer wajib menyertakan video packing dan link folder Google Drive yang dapat diakses CS.

## Perubahan Odoo

- `unitrade_theme/controllers/legal.py`
- `unitrade_theme/views/legal_templates.xml`
- Jika diperlukan, tambah anchor khusus:
  - `/legal?section=catalog-protection`
  - `/legal?section=refund-policy`

## Acceptance Criteria

- FAQ menjelaskan proteksi hanya untuk checkout website.
- FAQ menjelaskan transaksi luar website tidak dilindungi.
- FAQ menjelaskan fee upload produk.
- FAQ menjelaskan cancel 10 menit.
- FAQ menjelaskan refund evidence wajib.
- Copy legal mudah dirujuk dari detail produk, checkout, dan refund form.

## Urutan Implementasi

1. Tambah section legal di controller.
2. Tambah anchor/link section di template.
3. Link dari detail produk label proteksi.
4. Link dari checkout protection notice.
5. Link dari refund form.
6. Review copy bersama stakeholder.

