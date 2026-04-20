# UniTrade Marketplace 🛒

UniTrade adalah platform marketplace C2C (Customer-to-Customer) eksklusif yang dirancang khusus untuk mahasiswa **UNISA Yogyakarta**. Platform ini memungkinkan mahasiswa untuk jual-beli produk (makanan, fashion, elektronik, barang bekas) dan jasa dengan aman melalui verifikasi identitas mahasiswa (KTM).

## 🚀 Fitur Utama
- **Marketplace Mahasiswa**: Jual-beli barang kebutuhan kuliah dan gaya hidup mahasiswa.
- **Verifikasi KTM**: Keamanan transaksi dengan verifikasi Kartu Tanda Mahasiswa menggunakan OCR.
- **UI Modern**: Desain antarmuka yang bersih dan responsif menggunakan Tailwind CSS.
- **Sistem Seller**: Dashboard khusus bagi mahasiswa yang ingin berjualan.

## 🛠️ Tech Stack
- **Backend/Core**: Odoo 17.0
- **Frontend**: Odoo QWeb Templates & Tailwind CSS
- **Database**: PostgreSQL
- **Language**: Python, XML, JavaScript

## 📂 Struktur Folder
- `unitrade_theme/`: Modul untuk kustomisasi tampilan (UI/UX, CSS, Header, Footer).
- `unitrade_seller/`: Manajemen akun penjual dan toko mahasiswa.
- `unitrade_product_ext/`: Ekstensi model produk untuk fitur marketplace.
- `unitrade_delivery/`: Manajemen status pengiriman.
- `unitrade_payment/`: Integrasi sistem pembayaran (Midtrans/Manual).

## 💻 Cara Menjalankan Project

### 1. Prasyarat
- Pastikan Odoo 17 terinstal di sistem Anda (Windows/Linux).
- Database PostgreSQL aktif.

### 2. Konfigurasi
Gunakan file `odoo.conf` yang telah disediakan dan pastikan `addons_path` mengarah ke folder project ini.

### 3. Update Module & Tailwind
Setiap kali ada perubahan pada XML atau CSS, jalankan perintah berikut:

**Upgrade Modul Odoo:**
```powershell
# Jalankan via PowerShell
& "C:\Program Files\Odoo 17.0.20260217\python\python.exe" "C:\Program Files\Odoo 17.0.20260217\server\odoo-bin" -c "C:\Program Files\Odoo 17.0.20260217\server\odoo.conf" -d unitrade_db -u unitrade_theme --stop-after-init
```

**Rebuild Tailwind CSS:**
```bash
npx tailwindcss -i ./unitrade_theme/static/src/css/input.css -o ./unitrade_theme/static/src/css/output.css
```

## 📝 Catatan Pengembangan
- Hindari mengedit file core Odoo.
- Selalu gunakan prefix `tw-` untuk kelas Tailwind CSS agar tidak bentrok dengan Bootstrap bawaan Odoo.
- Pastikan font **Urbanist** terload dengan benar untuk menjaga konsistensi desain Figma.

---
© 2025 UniTrade Dev Team
