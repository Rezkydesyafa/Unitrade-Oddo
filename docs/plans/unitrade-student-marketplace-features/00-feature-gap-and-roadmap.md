# Feature Gap and Roadmap

Status: Draft
Scope: Konsep UniTrade sebagai katalog mahasiswa dan marketplace checkout terproteksi

## Keputusan Produk

- Mode katalog tetap diizinkan.
- Transaksi luar website wajib diberi label: tidak dilindungi escrow/refund UniTrade.
- Fee upload produk wajib dibayar sebelum produk publish.
- Payout seller dimulai manual oleh admin.
- Proteksi UniTrade hanya berlaku untuk checkout website.

## Fitur yang Sudah Ada Sebagian

| Fitur | Status |
| --- | --- |
| Verifikasi seller via KTM/OCR | Ada |
| Katalog produk dan filter | Ada |
| Detail produk | Ada |
| Cart | Ada |
| Chat buyer-seller | Ada |
| Wishlist | Ada |
| Review produk | Ada |
| Seller dashboard | Ada sebagian |
| Midtrans webhook | Ada sebagian |
| Delivery model | Ada sebagian |
| Notification model | Ada sebagian |

## Fitur yang Harus Dibuat

| Prioritas | Fitur | Alasan |
| --- | --- | --- |
| P0 | Label proteksi katalog | Wajib agar user paham beda transaksi luar website vs checkout website |
| P0 | Seller product CRUD website | Seller mahasiswa harus bisa upload produk tanpa backend Odoo |
| P0 | Fee upload produk sebelum publish | Model bisnis utama platform |
| P0 | Payment flow untuk listing fee | Produk tidak publish sebelum fee lunas |
| P1 | Checkout website penuh | Jalur resmi proteksi UniTrade |
| P1 | Escrow ledger | Dana buyer harus tertahan sampai selesai |
| P1 | Seller upload bukti serah/kirim | Trigger buyer confirmation dan auto complete |
| P1 | Buyer konfirmasi pesanan selesai | Trigger release dana seller |
| P1 | Auto complete 24 jam | Mencegah dana tertahan terlalu lama |
| P1 | Cancel window 10 menit | Aturan pembatalan cepat |
| P1 | Banding cancel setelah 10 menit | Aturan pembatalan setelah seller mulai proses |
| P1 | Refund/dispute dengan video unboxing | Proteksi buyer dan seller |
| P2 | Manual payout seller | Rilis dana secara terkendali |
| P2 | Notification center | User tahu status order/refund/payout |
| P2 | Legal/FAQ refund dan transaksi luar website | Mengurangi dispute karena ekspektasi salah |

## Roadmap Implementasi

### Fase 1: Katalog dan Listing Fee

- Label proteksi katalog.
- Seller product CRUD website.
- Tier fee upload produk.
- Payment listing fee.
- Produk publish setelah fee paid.

### Fase 2: Checkout Terproteksi

- Payment intent checkout website.
- Escrow ledger.
- Status order UniTrade.
- Seller upload bukti serah/kirim.
- Buyer klik pesanan selesai.
- Auto complete 24 jam.

### Fase 3: Cancel, Banding, Refund

- Cancel langsung sebelum 10 menit.
- Form banding setelah 10 menit.
- Modul dispute/refund.
- Upload video unboxing.
- Video packing dan link Google Drive untuk pengembalian.
- Dashboard CS.

### Fase 4: Manual Payout dan Notifikasi

- Rekening seller.
- Saldo tertahan/siap cair/sudah cair.
- Admin payout manual.
- Notification center.
- Legal/FAQ final.

## Modul Odoo Terkait

- `unitrade_theme`: UI website, label proteksi, order pages.
- `unitrade_seller`: seller dashboard, product upload, rekening, payout context.
- `unitrade_product_ext`: product listing status dan fee fields.
- `unitrade_payment`: payment intent, Midtrans, escrow ledger.
- `unitrade_delivery`: bukti serah/kirim dan auto complete.
- `unitrade_dispute`: modul baru untuk banding/refund.
- `unitrade_notification`: inbox dan event notification.

