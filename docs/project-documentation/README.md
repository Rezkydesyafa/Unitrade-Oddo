# Dokumentasi Project UniTrade Odoo 17

Dokumentasi ini dibuat sebagai bahan belajar kode dan alur sistem UniTrade. Jumlah file sengaja dibuat sedikit supaya tidak membingungkan, tetapi isi tetap detail: ada penjelasan fitur, module, class, function, service, route, database table, ERD, dan panduan maintenance.

## Struktur Dokumentasi

| File | Fokus |
| --- | --- |
| `01-project-overview-architecture.md` | Gambaran umum project, istilah, struktur folder, module map, dan arsitektur |
| `02-database-erd.md` | Daftar model/tabel database, ERD, field relasi, state penting, dan cara debug data |
| `03-feature-workflows.md` | Cara kerja fitur dari sisi user, seller, admin, payment, chat, review, CS, dan notifikasi |
| `04-code-map-functions.md` | Peta module, class, controller, route, function penting, service, dan cara membaca kode |
| `05-maintenance-deploy.md` | Integrasi eksternal, config, logging, testing, upgrade module, deploy, dan troubleshooting |

## Cara Membaca Sesuai Kebutuhan

Untuk anggota non-IT:

1. Mulai dari `01-project-overview-architecture.md`.
2. Lanjut ke `03-feature-workflows.md`.
3. Buka `02-database-erd.md` hanya jika ingin tahu data apa yang tersimpan.

Untuk belajar kode:

1. Mulai dari `01-project-overview-architecture.md`.
2. Buka `04-code-map-functions.md` untuk melihat class, route, function, dan service.
3. Cocokkan dengan `02-database-erd.md` untuk memahami tabel yang berubah.
4. Pakai `03-feature-workflows.md` untuk memahami urutan bisnisnya.

Untuk debugging:

1. Cari fitur di `03-feature-workflows.md`.
2. Cari route/function di `04-code-map-functions.md`.
3. Cek tabel/model di `02-database-erd.md`.
4. Cek panduan operasional di `05-maintenance-deploy.md`.

## Ringkasan UniTrade

UniTrade adalah marketplace C2C berbasis Odoo 17 untuk mahasiswa UNISA Yogyakarta. Pembeli dapat belanja seperti marketplace biasa. Penjual wajib verifikasi KTM sebelum bisa menjual. Payment memakai Midtrans, dana ditahan di escrow internal, lalu dicairkan ke seller lewat payout manual oleh admin.

Module utama:

| Module | Peran |
| --- | --- |
| `unitrade_theme` | Website utama, login, OTP, profile, cart, checkout, customer service |
| `unitrade_seller` | Seller onboarding, verifikasi KTM, dashboard seller |
| `unitrade_product_ext` | Field marketplace pada produk |
| `unitrade_payment` | Midtrans, escrow, order status, payout, voucher |
| `unitrade_delivery` | Pengiriman dan bukti serah terima |
| `unitrade_dispute` | Refund dan dispute |
| `unitrade_chat` | Chat buyer-seller |
| `unitrade_notification` | Notifikasi user, seller, admin |
| `unitrade_review` | Review, helpful vote, report ulasan |
| `unitrade_wishlist` | Wishlist produk |
| `unitrade_cs_ai` | Customer service AI dan eskalasi admin |
| `unitrade_admin` | Dashboard admin dan action admin |

## Prinsip Saat Mengubah Kode

- Jangan hardcode credential API. Gunakan `ir.config_parameter`.
- Model baru wajib punya entry di `security/ir.model.access.csv`.
- Gunakan `_logger`, bukan `print()`.
- Gunakan `sudo()` hanya jika benar-benar perlu.
- Untuk class Tailwind di project ini, gunakan prefix `tw-`.
- Setelah mengubah model, view, security, atau asset, upgrade module terkait.

## Status

Dokumentasi ini disusun dari struktur kode lokal di repository saat ini. Beberapa bagian menjelaskan implementasi yang ada sekarang, bukan asumsi fitur ideal.
