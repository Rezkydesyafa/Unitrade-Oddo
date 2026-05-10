# Seller Product Upload Fee Plan

Status: Draft
Priority: P0

## Tujuan

Seller mahasiswa terverifikasi dapat upload produk dari website, tetapi produk baru hanya publish setelah fee upload produk dibayar.

## Keputusan Produk

- Seller wajib verifikasi KTM.
- Fee upload wajib sebelum produk publish.
- Fee dihitung dari harga produk dalam Rupiah.
- Tarif awal disimpan sebagai konfigurasi admin.
- Produk yang fee-nya belum lunas berstatus `fee_pending`.

## Tarif Fee

| Rentang harga produk | Tarif default |
| --- | ---: |
| Rp1 - Rp50.000 | 3% |
| Rp50.001 - Rp100.000 | 5% |
| Rp100.001 - Rp500.000 | 7% |
| Rp500.001 ke atas | 10% |

Catatan: tier pertama bisa dibuat configurable agar admin dapat memilih 2,5% atau 3%.

## Status Saat Ini

- Seller verification sudah ada.
- Seller dashboard sudah ada.
- Product marketplace model sudah ada.
- Seller normal belum bisa create/write product via website.
- ACL product seller saat ini read-only.
- Fee upload produk belum ada.

## Scope MVP

- Website form tambah produk untuk seller verified.
- Website form edit produk terbatas untuk produk milik seller.
- Hitung fee berdasarkan harga.
- Simpan produk sebagai draft/fee pending.
- Buat payment listing fee.
- Publish produk setelah fee paid.
- Admin dapat melihat status fee.

## Data Model

Tambahan field di `product.template`:

- `x_listing_status`: draft, fee_pending, published, rejected, archived.
- `x_listing_fee_rate`: Float.
- `x_listing_fee_amount`: Monetary.
- `x_listing_fee_status`: unpaid, pending, paid, failed, waived.
- `x_listing_fee_payment_id`: Many2one ke payment intent.
- `x_listing_fee_paid_at`: Datetime.
- `x_listing_fee_tier_label`: Char.

Model konfigurasi:

- `unitrade.listing.fee.tier`
  - `min_price`
  - `max_price`
  - `rate`
  - `active`
  - `sequence`

## Controller dan Routes

- `GET /seller/products/new`
- `POST /seller/products/create`
- `GET /seller/products/<id>/edit`
- `POST /seller/products/<id>/update`
- `POST /seller/products/<id>/pay-fee`
- `GET /seller/products/<id>/fee`

## Acceptance Criteria

- User non-seller tidak bisa upload produk.
- Seller unverified diarahkan ke seller onboarding.
- Seller verified bisa membuat produk dari website.
- Produk baru tidak muncul di shop sebelum fee paid.
- Fee ditampilkan sebelum seller membayar.
- Fee tersimpan dalam format Rupiah tanpa desimal.
- Setelah webhook payment fee sukses, produk otomatis publish.
- Seller hanya bisa edit produk miliknya.

## Urutan Implementasi

1. Buat model fee tier dan data default.
2. Extend `product.template` untuk listing status dan fee.
3. Tambah controller website product CRUD.
4. Tambah templates seller product form.
5. Tambah payment intent listing fee.
6. Update webhook payment untuk publish produk setelah fee paid.
7. Tambah menu dashboard seller untuk produk.
8. Test permission seller/admin.

