# Product and Listing Fee Management Plan

Status: Updated after source audit
Priority: P0
Last reviewed: 2026-05-18

## Update 2026-05-18

Product dan listing fee sudah ada sebagian. `product.template` sudah punya `x_is_marketplace`, `x_seller_id`, `x_listing_fee`, `x_listing_expires_at`, stock field, publish/unpublish action, dan backend view `Produk Marketplace`. Seller website flow juga membuat produk draft unpublished lalu membuat `unitrade.payment.intent` dengan `intent_type = listing_fee`; produk publish setelah intent paid.

Koreksi terhadap plan lama:

- Plan lama mengusulkan tier persentase `unitrade.listing.fee.tier`, tetapi source saat ini memakai config sederhana: `unitrade.seller.listing_fee.threshold`, `unitrade.seller.listing_fee.low_amount`, `unitrade.seller.listing_fee.high_amount`, dan `unitrade.seller.posting_admin_fee`.
- Belum ada field status listing/fee eksplisit. Status masih disimpulkan dari `sale_ok`, `website_published`, `x_listing_expires_at`, dan payment intent.
- Admin view produk belum menampilkan riwayat payment intent listing fee secara langsung.
- Action waive/reject belum ada dan harus dibuat dengan alasan wajib plus audit log.

Rekomendasi MVP: tambah field operasional minimal di `product.template`:

- `x_listing_status`: draft, fee_pending, published, rejected, archived, expired.
- `x_listing_fee_status`: not_required, unpaid, pending, paid, failed, waived.
- `x_listing_fee_payment_id`: Many2one ke `unitrade.payment.intent`.
- `x_listing_fee_paid_at`, `x_listing_fee_waived_by_id`, `x_listing_fee_waive_reason`.

Fee tier model boleh ditunda. Lebih aman exposing config yang sudah ada lewat settings dulu, lalu migrate ke tier model jika product decision memang berubah ke persentase.

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
- Fee policy/tier label.
- Nominal fee.
- Status fee.
- Status publish.
- Tanggal upload.
- Tanggal publish.
- Alasan reject jika ada.

## Perubahan Odoo

- Extend `product.template` dengan field listing fee.
- Tambah status listing/fee eksplisit di `product.template`.
- Tambah smart button produk ke payment intent listing fee.
- Tambah settings UI untuk config fee yang sudah ada.
- Tambah model `unitrade.listing.fee.tier` hanya jika fee persentase/tier dinyatakan sebagai keputusan produk baru.
- Tambah action admin untuk approve/reject/waive fee.
- Hubungkan payment intent listing fee ke produk.
- Tambah audit event untuk reject, waive, publish manual, dan unpublish manual.

## Acceptance Criteria

- Produk belum fee paid tidak publish.
- Admin dapat melihat produk fee pending.
- Admin dapat melihat jumlah fee upload per produk.
- Admin dapat reject produk dengan alasan.
- Admin dapat waive fee dengan alasan dan audit log.
- Seller mendapat notifikasi jika produk publish/rejected.
