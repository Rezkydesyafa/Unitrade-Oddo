# UniTrade Marketplace

UniTrade adalah marketplace C2C berbasis Odoo 17 untuk mahasiswa Yogyakarta. Platform ini membantu user terdaftar membeli produk, menyimpan wishlist, chat dengan seller, melakukan pembayaran, dan memberi review. User yang ingin berjualan harus melakukan verifikasi seller menggunakan KTM agar marketplace tetap aman dan relevan untuk lingkungan kampus.

## Ringkasan Project

| Bagian            | Keterangan                                                  |
| ----------------- | ----------------------------------------------------------- |
| Nama project      | UniTrade Marketplace                                        |
| Target pengguna   | Mahasiswa dan user terdaftar di lingkungan UNISA Yogyakarta |
| Platform          | Odoo 17 Website dan Website Sale                            |
| Model bisnis      | Marketplace C2C                                             |
| Verifikasi seller | Verifikasi KTM dan validasi data mahasiswa                  |
| Pembayaran        | Integrasi Midtrans                                          |
| Frontend          | QWeb, OWL, JavaScript, Tailwind CSS dengan prefix `tw-`     |
| Database          | PostgreSQL                                                  |

## Fitur Utama

- **Autentikasi user**: register, login, verifikasi OTP, dan reset password.
- **Profil user**: pengelolaan data pribadi, nomor HP, alamat, dan lokasi.
- **Daftar seller**: pengajuan seller, upload KTM, validasi NIM, dan persetujuan admin.
- **Marketplace produk**: katalog produk, detail produk, kondisi barang, stok, lokasi, dan foto produk.
- **Filter pencarian**: pencarian produk berdasarkan kata kunci, kategori, harga, kondisi, dan lokasi.
- **Wishlist**: user dapat menyimpan produk yang ingin dilihat atau dibeli nanti.
- **Chat buyer dan seller**: percakapan berdasarkan produk, lampiran gambar, dan laporan chat.
- **Checkout dan pembayaran**: proses pesanan dan pembayaran melalui Midtrans.
- **Review produk**: rating, komentar, tag review, dan foto review setelah pembelian.
- **Notifikasi**: pemberitahuan terkait aktivitas penting seperti akun, pesanan, dan pembayaran.

## Dokumentasi

Dokumentasi berikut dibuat dalam format Markdown dan Mermaid. Jika repository di-upload ke GitHub, diagram Mermaid di file `.md` akan tampil otomatis sebagai diagram.

| Dokumen                                              | Isi                                                                                                                                                    |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [Flowchart Fitur](./FEATURE_FLOWCHARTS.md)           | Diagram alur untuk fitur yang sudah selesai, seperti login, register, daftar seller, profil, filter pencarian, wishlist, chat, pembayaran, dan review. |
| [ERD UniTrade](./FEATURE_ERD.md)                     | Diagram hubungan data utama project dengan bahasa umum yang mudah dipahami.                                                                            |
| [Viewer Flowchart](./FEATURE_FLOWCHARTS_VIEWER.html) | Halaman HTML lokal untuk membuka flowchart dengan tampilan Mermaid di browser.                                                                         |

## Struktur Modul

| Modul                   | Fungsi utama                                                                                                         |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `unitrade_theme`        | Tampilan website, halaman utama, navbar, shop, produk, login, OTP, profil, cart, dan halaman legal.                  |
| `unitrade_seller`       | Pendaftaran seller, verifikasi KTM, validasi data mahasiswa, status seller, dan dashboard admin.                     |
| `unitrade_product_ext`  | Pengembangan data produk marketplace seperti seller, kondisi barang, lokasi, stok, spesifikasi, dan tampilan produk. |
| `unitrade_payment`      | Integrasi pembayaran dan halaman checkout.                                                                           |
| `unitrade_wishlist`     | Penyimpanan produk favorit user.                                                                                     |
| `unitrade_review`       | Rating dan review produk dari pembeli.                                                                               |
| `unitrade_chat`         | Chat buyer-seller, pesan produk, lampiran gambar, pembatasan spam, dan laporan chat.                                 |
| `unitrade_notification` | Notifikasi sistem untuk aktivitas penting user.                                                                      |

## Alur Utama Aplikasi

1. User membuat akun dan melakukan verifikasi OTP.
2. User melengkapi profil dan alamat.
3. User dapat mencari produk, melihat detail produk, menyimpan wishlist, atau menghubungi seller.
4. User yang ingin berjualan mengajukan verifikasi seller dengan KTM.
5. Admin memeriksa pengajuan seller dan menyetujui atau menolak pengajuan.
6. Seller yang disetujui dapat membuat dan mengelola produk.
7. Buyer membuat pesanan dan menyelesaikan pembayaran.
8. Buyer dapat memberi review setelah pembelian.
9. Sistem mengirim notifikasi untuk aktivitas penting.

## Tech Stack

- **Backend**: Odoo 17, Python
- **Frontend**: Odoo QWeb, OWL, JavaScript
- **Styling**: Tailwind CSS dengan prefix `tw-`
- **Database**: PostgreSQL
- **Payment Gateway**: Midtrans
- **OCR KTM**: google vision API

## Prasyarat

Pastikan environment berikut sudah tersedia:

- Odoo 17
- PostgreSQL
- Node.js dan npm untuk build Tailwind CSS
- Database Odoo yang sudah dibuat
- Konfigurasi `odoo.conf` dengan `addons_path` mengarah ke folder project ini

## Cara Menjalankan Project

### 1. Install atau upgrade modul Odoo

Contoh perintah PowerShell untuk upgrade modul utama:

```powershell
& "C:\Program Files\Odoo 17.0.20260217\python\python.exe" "C:\Program Files\Odoo 17.0.20260217\server\odoo-bin" -c "C:\Program Files\Odoo 17.0.20260217\server\odoo.conf" -d unitrade_db -u unitrade_theme,unitrade_seller,unitrade_product_ext,unitrade_payment,unitrade_wishlist,unitrade_review,unitrade_chat,unitrade_notification --stop-after-init
```

Sesuaikan nama database, lokasi instalasi Odoo, dan daftar modul jika environment berbeda.

### 2. Build Tailwind CSS

Jalankan perintah berikut setiap ada perubahan pada file Tailwind:

```bash
npx tailwindcss -i ./unitrade_theme/static/src/css/input.css -o ./unitrade_theme/static/src/css/output.css
```

### 3. Jalankan server Odoo

Contoh perintah PowerShell:

```powershell
& "C:\Program Files\Odoo 17.0.20260217\python\python.exe" "C:\Program Files\Odoo 17.0.20260217\server\odoo-bin" -c "C:\Program Files\Odoo 17.0.20260217\server\odoo.conf" -d unitrade_db --http-port=8069
```

Setelah server berjalan, buka:

```text
http://127.0.0.1:8069
```

## Aturan Pengembangan

- Jangan mengubah file core Odoo.
- Selalu gunakan prefix `tw-` untuk class Tailwind.
- Simpan credential API di `ir.config_parameter`, bukan hardcode di kode.
- Setiap model baru wajib memiliki akses di `security/ir.model.access.csv`.
- Setiap folder `models/` dan `controllers/` wajib memiliki `__init__.py`.
- Gunakan `_logger` untuk logging, bukan `print()`.
- Gunakan `sudo()` hanya jika memang perlu melewati aturan akses.
- Jaga penamaan, alur data, dan tampilan agar konsisten dengan dokumentasi ERD dan flowchart.

## Catatan untuk Kontributor

Sebelum menambah fitur baru, cek dulu dokumentasi berikut:

- [Flowchart Fitur](./FEATURE_FLOWCHARTS.md)
- [ERD UniTrade](./FEATURE_ERD.md)

Jika fitur baru menambah alur proses atau data baru, update dokumentasi terkait agar README, flowchart, dan ERD tetap selaras.
