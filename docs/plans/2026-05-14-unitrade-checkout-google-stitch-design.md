# UniTrade Checkout UI Design for Google Stitch

Tanggal: 2026-05-14
Status: Draft UI prompt
Target: Google Stitch

## Tujuan

Membuat draft UI halaman checkout UniTrade yang senada dengan halaman cart, shop, dan product detail yang sudah ada. Checkout ini khusus untuk transaksi resmi melalui website UniTrade dengan proteksi escrow. Tidak ada pengiriman, kurir, GoSend, ongkir, tracking, atau alamat pengiriman.

Checkout harus terasa seperti halaman operasional ecommerce yang bersih, bukan landing page. Buyer harus langsung memahami produk yang dibeli, cara serah terima manual, proteksi UniTrade, metode pembayaran, dan total yang harus dibayar.

## Prinsip Produk

- Transaksi checkout website adalah jalur resmi yang mendapat proteksi UniTrade.
- Dana buyer ditahan sebagai escrow sampai transaksi selesai.
- Seller dan buyer melakukan serah terima manual, biasanya di area kampus.
- Detail koordinasi serah terima dilakukan melalui chat setelah pembayaran berhasil.
- Transaksi di luar website tidak mendapat proteksi escrow/refund UniTrade.
- Halaman checkout tidak membahas GoSend, delivery, ongkir, kurir, nomor resi, atau tracking.

## Gaya Visual

- Background halaman: soft light gray `#f5f5f7`.
- Container utama: putih, rounded besar, padding luas, center aligned.
- Card: putih, border tipis `#f0f0f0`, shadow halus, radius sekitar 16px.
- Typography: Urbanist atau rounded sans-serif sejenis.
- Warna teks utama: `#212529`.
- Warna teks muted: `#6b7280`.
- Tombol utama: background `#212529`, teks putih, bentuk pill.
- Tombol secondary: putih, border `#212529`, teks `#212529`.
- Hindari gradient besar, blob dekoratif, hero marketing, dan ilustrasi berlebihan.
- Jika Google Stitch menghasilkan Tailwind, semua utility class wajib memakai prefix `tw-`.

## Layout Desktop

Canvas target sekitar 1440px. Halaman menggunakan white main container seperti cart page. Di dalamnya ada breadcrumb di atas, judul halaman, lalu layout dua kolom.

Kolom kiri sekitar 65 persen lebar halaman. Kolom ini berisi informasi utama checkout: produk, serah terima, proteksi UniTrade, dan metode pembayaran.

Kolom kanan sekitar 35 persen lebar halaman. Kolom ini berupa sticky summary card yang berisi total pembayaran dan tombol utama.

## Layout Mobile

Pada mobile, semua section menjadi satu kolom. Urutan mobile:

1. Breadcrumb.
2. Judul Checkout.
3. Produk Dibeli.
4. Serah Terima.
5. Proteksi UniTrade.
6. Metode Pembayaran.
7. Ringkasan Pesanan.

Tombol `Bayar Sekarang` full width. Semua teks harus tetap terbaca dan tidak overflow.

## Struktur UI

### 1. Breadcrumb

Gunakan breadcrumb card kecil seperti halaman cart:

- Icon home.
- `Beranda`
- `Keranjang`
- `Checkout`

Checkout menjadi item aktif dengan teks dark/bold.

### 2. Page Title

Judul utama:

`Checkout`

Subcopy pendek opsional:

`Selesaikan pembayaran untuk mendapat proteksi transaksi UniTrade.`

### 3. Product Review Card

Judul section:

`Produk Dibeli`

Isi card:

- Thumbnail produk.
- Nama produk: `Laptop ASUS VivoBook`.
- Deskripsi pendek: `Laptop modern dengan desain tipis dan performa responsif untuk produktivitas harian.`
- Seller: `Dijual oleh Andi Store`.
- Kuantitas: `Qty 1`.
- Harga: `Rp 15.000.000`.

Catatan desain:

- Styling mengikuti cart item yang sudah ada.
- Nama produk dan harga menggunakan warna `#212529`.
- Deskripsi dan seller menggunakan muted text.

### 4. Handoff Method Card

Judul section:

`Serah Terima`

Status utama:

`Janji temu langsung dengan seller`

Deskripsi:

`Atur titik temu dan waktu melalui chat setelah pembayaran berhasil.`

Informasi area:

`Area seller: Kampus UNISA Yogyakarta`

Kontrol:

- Textarea kecil dengan label `Catatan untuk seller`.
- Placeholder: `Contoh: bisa bertemu sore hari di area kampus`.
- Tombol secondary: `Chat Seller`.

Catatan desain:

- Jangan tampilkan alamat pengiriman.
- Jangan tampilkan pilihan kurir.
- Jangan tampilkan ongkir.
- Buat section ini terasa seperti pilihan serah terima lokal, bukan delivery form.

### 5. UniTrade Protection Card

Judul section:

`Proteksi UniTrade`

Tampilkan tiga poin ringkas dengan icon sederhana:

1. `Dana ditahan aman sampai pesanan selesai`
2. `Seller wajib upload bukti serah terima`
3. `Buyer bisa konfirmasi selesai atau ajukan bantuan jika ada masalah`

Info box:

`Transaksi di luar website tidak mendapat proteksi escrow UniTrade.`

Catatan desain:

- Card ini harus terlihat informatif, bukan menakutkan.
- Gunakan warna netral, bukan warning merah besar.
- Boleh pakai border lembut dan background `#f8fafc`.

### 6. Payment Method Card

Judul section:

`Metode Pembayaran`

Metode aktif:

`Midtrans`

Subcopy:

`Pilih metode pembayaran pada halaman Midtrans setelah klik Bayar Sekarang.`

Pill kecil:

- `QRIS`
- `Virtual Account`
- `E-Wallet`

Catatan desain:

- Jangan tampilkan form kartu kredit.
- Jangan tampilkan input rekening.
- Fokus ke payment gateway handoff.

### 7. Sticky Order Summary

Judul:

`Ringkasan Pesanan`

Rows:

- `Subtotal` - `Rp 15.000.000`
- `Biaya Layanan` - `Rp 0`
- `Pajak` - `Rp 1.650.000`
- Divider
- `Total` - `Rp 16.650.000`

Voucher:

- Input placeholder: `Kode voucher...`
- Tombol: `Terapkan`

Primary CTA:

`Bayar Sekarang`

Secure note:

`Pembayaran diproses aman melalui Midtrans`

Secondary link:

`Kembali ke Keranjang`

Catatan desain:

- Summary card harus mirip dengan ringkasan pesanan di halaman cart.
- CTA utama hitam, pill, full width.
- Total harus paling menonjol.

## Copy UI Final

- `Checkout`
- `Produk Dibeli`
- `Serah Terima`
- `Janji temu langsung dengan seller`
- `Atur titik temu dan waktu melalui chat setelah pembayaran berhasil.`
- `Area seller: Kampus UNISA Yogyakarta`
- `Catatan untuk seller`
- `Chat Seller`
- `Proteksi UniTrade`
- `Dana ditahan aman sampai pesanan selesai`
- `Seller wajib upload bukti serah terima`
- `Buyer bisa konfirmasi selesai atau ajukan bantuan jika ada masalah`
- `Transaksi di luar website tidak mendapat proteksi escrow UniTrade.`
- `Metode Pembayaran`
- `Pilih metode pembayaran pada halaman Midtrans setelah klik Bayar Sekarang.`
- `Ringkasan Pesanan`
- `Biaya Layanan`
- `Bayar Sekarang`
- `Pembayaran diproses aman melalui Midtrans`
- `Kembali ke Keranjang`

## Prompt Google Stitch

```text
Create a modern checkout page UI for UniTrade Marketplace, a C2C student marketplace for UNISA Yogyakarta.

The checkout page is for official website transactions protected by UniTrade escrow payment. There is no shipping or delivery service. Do not show courier, delivery fee, shipping address, GoSend, tracking number, logistics status, or delivery address fields. Product handoff is manual between buyer and seller, usually around campus.

Match the existing UniTrade visual style:
- Soft light gray page background #f5f5f7
- Large centered white rounded container
- Clean white cards with subtle #f0f0f0 border and soft shadow
- Urbanist or similar rounded sans-serif typography
- Main text color #212529 or near black
- Muted text #6b7280
- Primary buttons black/dark #212529 with white text
- Outline buttons white background, dark border, dark text
- Calm, minimal, premium marketplace feel
- Similar mood to a clean Apple-like ecommerce UI
- Avoid colorful gradients, decorative blobs, and marketing hero sections

Desktop layout:
- Canvas width around 1440px
- White main container with generous padding
- Breadcrumb card at top left: home icon, Beranda, Keranjang, Checkout
- Page title: Checkout
- Two-column layout:
  - Left column width about 65%
  - Right column width about 35%, sticky order summary

Left column sections:

1. Product Review Card
- Section title: Produk Dibeli
- Product thumbnail
- Product name: Laptop ASUS VivoBook
- Short description: Laptop modern dengan desain tipis dan performa responsif untuk produktivitas harian.
- Seller name: Dijual oleh Andi Store
- Quantity: Qty 1
- Price: Rp 15.000.000
- Use compact card styling similar to the cart page

2. Handoff Method Card
- Section title: Serah Terima
- Selected option: Janji temu langsung dengan seller
- Description: Atur titik temu dan waktu melalui chat setelah pembayaran berhasil.
- Seller area: Area seller: Kampus UNISA Yogyakarta
- Small note textarea with label: Catatan untuk seller
- Textarea placeholder: Contoh: bisa bertemu sore hari di area kampus
- Secondary outline button: Chat Seller
- No shipping address fields
- No courier options
- No delivery fee

3. UniTrade Protection Card
- Section title: Proteksi UniTrade
- Three concise rows with icons:
  - Dana ditahan aman sampai pesanan selesai
  - Seller wajib upload bukti serah terima
  - Buyer bisa konfirmasi selesai atau ajukan bantuan jika ada masalah
- Add a subtle info box: Transaksi di luar website tidak mendapat proteksi escrow UniTrade.

4. Payment Method Card
- Section title: Metode Pembayaran
- Selected payment method: Midtrans
- Description: Pilih metode pembayaran pada halaman Midtrans setelah klik Bayar Sekarang.
- Show supported methods as small muted pills: QRIS, Virtual Account, E-Wallet
- Keep the UI simple, no full payment form

Right sticky summary card:
- Title: Ringkasan Pesanan
- Rows:
  - Subtotal: Rp 15.000.000
  - Biaya Layanan: Rp 0
  - Pajak: Rp 1.650.000
  - Total: Rp 16.650.000
- Voucher input with placeholder: Kode voucher...
- Black Terapkan button
- Large pill-shaped black primary button: Bayar Sekarang
- Small secure note below: Pembayaran diproses aman melalui Midtrans
- Link below: Kembali ke Keranjang

Mobile layout:
- Single column
- Summary appears after product and protection sections
- Primary button full width
- Text must not overflow

Use Indonesian UI copy. Keep it realistic for an Odoo marketplace checkout page. If generating Tailwind classes, use the `tw-` prefix for every Tailwind utility.
```

## Negative Prompt / Jangan Dibuat

- Jangan buat hero section.
- Jangan buat landing page.
- Jangan buat ilustrasi besar.
- Jangan tampilkan GoSend.
- Jangan tampilkan pilihan kurir.
- Jangan tampilkan ongkir.
- Jangan tampilkan alamat pengiriman.
- Jangan tampilkan tracking/resi.
- Jangan tampilkan checkout multi-step yang terlalu rumit.
- Jangan gunakan warna ungu atau biru dominan.
- Jangan gunakan card di dalam card secara berlebihan.

## Acceptance Criteria Draft UI

- Halaman terlihat satu keluarga dengan cart UniTrade.
- Buyer langsung tahu bahwa transaksi ini memakai escrow.
- Tidak ada elemen pengiriman/logistik.
- Ringkasan pesanan jelas dan sticky pada desktop.
- Tombol `Bayar Sekarang` menjadi CTA paling kuat.
- Copy UI seluruhnya dalam bahasa Indonesia.
- Layout desktop dan mobile tetap rapi.
