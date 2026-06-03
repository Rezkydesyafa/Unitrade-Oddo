# Catalog Mode and Protection Label Plan

Status: Draft
Priority: P0

## Tujuan

UniTrade tetap menjadi katalog produk mahasiswa. Buyer boleh menghubungi seller dan transaksi di luar website, tetapi UI harus jelas menyatakan bahwa transaksi luar website tidak mendapat proteksi escrow/refund UniTrade.

## Status Saat Ini

- Katalog, detail produk, seller profile, wishlist, dan chat sudah ada.
- Belum ada label eksplisit yang membedakan transaksi luar website dan checkout website.
- Chat seller bisa dianggap sebagai jalur transaksi, sehingga perlu disclaimer.

## Scope MVP

- Tambahkan label proteksi pada detail produk.
- Tambahkan label di sekitar tombol chat seller.
- Tambahkan informasi di cart/checkout bahwa proteksi berlaku jika pembayaran lewat website.
- Tambahkan FAQ/legal tentang transaksi luar website.

## Copy yang Disarankan

Label pendek:

`Transaksi luar website tidak dilindungi escrow/refund UniTrade. Gunakan checkout website untuk proteksi pembayaran.`

Detail legal:

`UniTrade menyediakan mode katalog agar mahasiswa dapat memasarkan produk. Jika pembeli dan seller memilih menyelesaikan transaksi di luar website, UniTrade tidak dapat menahan dana, memproses refund, atau memverifikasi penyelesaian pesanan. Proteksi UniTrade hanya berlaku untuk transaksi yang checkout dan dibayar melalui website.`

## Perubahan UI

- Detail produk:
  - Tampilkan badge kecil dekat area CTA.
  - Bedakan tombol `Chat Penjual` dan `Checkout via UniTrade`.
- Seller profile:
  - Tampilkan disclaimer sebelum buyer mulai chat.
- Chat:
  - Saat pertama membuka chat dari produk, tampilkan system note.
- FAQ/legal:
  - Tambah section `Transaksi Katalog dan Proteksi UniTrade`.

## Perubahan Odoo

- `unitrade_theme/views/product_templates.xml`
- `unitrade_seller/views/seller_templates.xml`
- `unitrade_chat/static/src/xml/chat.xml`
- `unitrade_theme/controllers/legal.py`
- `unitrade_theme/views/legal_templates.xml`

## Acceptance Criteria

- Buyer melihat label proteksi di detail produk.
- Buyer melihat bahwa chat/transaksi luar website tidak dilindungi escrow/refund.
- Checkout website tetap diposisikan sebagai jalur proteksi resmi.
- Copy legal tersedia di FAQ/syarat.
- Label tidak menghalangi CTA utama dan responsive di mobile.

## Urutan Implementasi

1. Tambah copy legal di controller/legal templates.
2. Tambah badge di detail produk.
3. Tambah disclaimer di seller profile/chat entry.
4. Test `/shop`, detail produk, seller profile, dan chat.

