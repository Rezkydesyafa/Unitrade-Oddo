# Product and Listing Fee Management Plan

Status: Draft
Priority: P0

## Tujuan

Admin dapat mengawasi produk marketplace, status publish, dan pembayaran fee upload produk sebelum produk muncul di katalog.

## Scope MVP

- Daftar produk marketplace.
- Filter produk berdasarkan status listing.
- Filter produk berdasarkan status fee.
- Detail produk dan seller.
- Review produk jika diperlukan.
- Approve/reject produk.
- Waive fee jika admin memberi pengecualian.
- Lihat riwayat pembayaran fee upload.

## Status Produk

- Draft.
- Fee pending.
- Fee paid.
- Published.
- Rejected.
- Archived.

## Data yang Ditampilkan

- Nama produk.
- Seller.
- Harga.
- Tier fee.
- Nominal fee.
- Status fee.
- Status publish.
- Tanggal upload.
- Tanggal publish.
- Alasan reject jika ada.

## Perubahan Odoo

- Extend `product.template` dengan field listing fee.
- Tambah model `unitrade.listing.fee.tier`.
- Tambah view admin untuk fee tier.
- Tambah action admin untuk approve/reject/waive fee.
- Hubungkan payment intent listing fee ke produk.

## Acceptance Criteria

- Produk belum fee paid tidak publish.
- Admin dapat melihat produk fee pending.
- Admin dapat melihat jumlah fee upload per produk.
- Admin dapat reject produk dengan alasan.
- Admin dapat waive fee dengan alasan dan audit log.
- Seller mendapat notifikasi jika produk publish/rejected.

