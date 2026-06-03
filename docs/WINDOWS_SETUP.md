# Setup UniTrade di Windows

Panduan ini untuk menjalankan UniTrade di Windows atau komputer lain tanpa menulis ulang command Odoo yang panjang. Entry point utama ada di:

```powershell
.\scripts\unitrade.ps1
```

Default script mengikuti environment lokal project ini:

- Odoo: `C:\Program Files\Odoo 17.0.20260217`
- Database: `unitrade_db`
- PostgreSQL user/password: `openpg` / `admin`
- Port Odoo: `8069`
- Config lokal yang digenerate: `tmp\odoo.unitrade.conf`
- Data dir lokal: `odoo_data`
- Log lokal: `logs`

Jika komputer lain punya path atau credential berbeda, override lewat parameter atau environment variable. Jangan commit credential asli ke repository.

## Prasyarat

Install dulu:

- Odoo 17 for Windows
- PostgreSQL yang bisa diakses oleh Odoo
- Node.js LTS dan npm
- Git

Pastikan PostgreSQL user punya akses ke database target. Untuk setup fresh, user perlu bisa membuat database atau database harus sudah dibuat dari pgAdmin/Odoo Database Manager.

## Setup Fresh

Jalankan semua command dari root project:

```powershell
cd D:\Unitrade_Oddo
```

Jika PowerShell memblokir script lokal:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

Generate config lokal:

```powershell
.\scripts\unitrade.ps1 config
```

Untuk komputer dengan lokasi Odoo atau credential PostgreSQL berbeda:

```powershell
.\scripts\unitrade.ps1 config `
  -OdooHome "C:\Program Files\Odoo 17.0.20260217" `
  -Database unitrade_db `
  -PgUser openpg `
  -PgPassword admin
```

Validasi environment:

```powershell
.\scripts\unitrade.ps1 doctor
```

Install dependency frontend dan build Tailwind:

```powershell
.\scripts\unitrade.ps1 install-node
.\scripts\unitrade.ps1 build
```

Install modul UniTrade ke database fresh:

```powershell
.\scripts\unitrade.ps1 install
```

Jika modul sudah pernah terinstall dan hanya perlu update kode/XML/data:

```powershell
.\scripts\unitrade.ps1 upgrade
```

Seed data testing dimulai dari dry-run:

```powershell
.\scripts\unitrade.ps1 seed-dry
```

Execute reset + seed:

```powershell
.\scripts\unitrade.ps1 seed
```

Task `seed` bersifat destructive untuk data marketplace testing UniTrade: produk seed, order seed, refund, chat, review, escrow ledger, payment intent, dan tiket customer service seed akan dibersihkan lalu dibuat ulang. Script seed tidak menghapus produk sistem seperti service/payment fee.

Jalankan server:

```powershell
.\scripts\unitrade.ps1 run
```

Buka:

```text
http://127.0.0.1:8069
```

## Workflow Development Harian

Terminal 1, jalankan Tailwind watch:

```powershell
.\scripts\unitrade.ps1 watch
```

Terminal 2, jalankan Odoo dengan mode dev assets/XML/QWeb:

```powershell
.\scripts\unitrade.ps1 run
```

Setelah mengubah file Python, XML view, security, atau manifest:

```powershell
.\scripts\unitrade.ps1 upgrade
```

Setelah mengubah class Tailwind di QWeb/OWL/JS:

```powershell
.\scripts\unitrade.ps1 build
```

atau biarkan task `watch` tetap berjalan.

## NPM Shortcut

Command yang sama juga tersedia dari `package.json`:

```powershell
npm.cmd run build
npm.cmd run watch
npm.cmd run odoo:doctor
npm.cmd run odoo:config
npm.cmd run odoo:install
npm.cmd run odoo:upgrade
npm.cmd run odoo:run
npm.cmd run seed:dry
npm.cmd run seed:reset
```

Parameter tambahan bisa diteruskan setelah `--`, contoh:

```powershell
npm.cmd run odoo:run -- -Port 8070
npm.cmd run odoo:upgrade -- -Modules unitrade_theme,unitrade_seller
```

Di PowerShell, gunakan `npm.cmd` jika `npm` biasa terkena error ExecutionPolicy karena shim `npm.ps1`.

## Modul Default

Task `install` dan `upgrade` menjalankan modul berikut dalam urutan dependency:

```text
unitrade,
unitrade_theme,
unitrade_seller,
unitrade_product_ext,
unitrade_payment,
unitrade_delivery,
unitrade_dispute,
unitrade_wishlist,
unitrade_review,
unitrade_chat,
unitrade_notification
```

Untuk upgrade modul tertentu:

```powershell
.\scripts\unitrade.ps1 upgrade -Modules unitrade_theme,unitrade_product_ext
```

## Override Environment

Selain parameter CLI, script membaca environment variable:

```powershell
$env:UNITRADE_ODOO_HOME = "C:\Program Files\Odoo 17.0.20260217"
$env:UNITRADE_DB_NAME = "unitrade_db"
$env:UNITRADE_DB_USER = "openpg"
$env:UNITRADE_DB_PASSWORD = "admin"
$env:UNITRADE_ODOO_CONF = "D:\Unitrade_Oddo\tmp\odoo.unitrade.conf"
$env:UNITRADE_MODULES = "unitrade_theme,unitrade_seller"
```

Lalu jalankan:

```powershell
.\scripts\unitrade.ps1 doctor
```

## Config Odoo

Task `config` membuat `tmp\odoo.unitrade.conf` dengan `addons_path` berisi:

```text
<OdooHome>\server\odoo\addons,
<OdooHome>\server\addons,
<root project UniTrade>
```

Jika menjalankan Odoo lewat Windows Service, pastikan service tersebut memakai config yang `addons_path`-nya juga mengarah ke root project ini. Task runner ini lebih cocok untuk development lokal karena menjalankan Odoo langsung dari terminal.

## Seed Akun Testing

Password default semua akun seed:

```text
UnitradeTest123!
```

Ubah password seed:

```powershell
.\scripts\unitrade.ps1 seed -SeedPassword "PasswordBaru123!"
```

Jalankan seed tanpa sample transaksi:

```powershell
.\scripts\unitrade.ps1 seed -SeedTransactions:$false
```

Detail akun testing ada di [UNITRADE_TEST_DATA_SEED.md](./UNITRADE_TEST_DATA_SEED.md).

## OCR dan API Eksternal

Credential API jangan ditulis di file project. Simpan lewat `ir.config_parameter` atau menu Settings Odoo sesuai modul terkait.

Untuk dependency OCR lokal, script lama masih tersedia:

```powershell
.\install_paddleocr.bat
```

Jalankan sebagai Administrator karena script menginstall package ke Python bawaan Odoo.

## Troubleshooting

Jika `doctor` gagal karena `odoo.conf` belum ada:

```powershell
.\scripts\unitrade.ps1 config
.\scripts\unitrade.ps1 doctor
```

Jika `install` gagal karena database belum ada, buat database dari Odoo Database Manager atau pgAdmin, lalu ulangi:

```powershell
.\scripts\unitrade.ps1 install
```

Jika asset frontend tidak berubah di browser:

```powershell
.\scripts\unitrade.ps1 build
.\scripts\unitrade.ps1 upgrade -Modules unitrade_theme
```

Lalu restart `run` dan refresh browser dengan cache disabled.

Log utama ada di folder `logs`, misalnya:

- `logs\install_unitrade_modules.log`
- `logs\upgrade_unitrade_modules.log`
- `logs\seed_unitrade_test_data_dry_run.log`
- `logs\seed_unitrade_test_data_execute.log`
- `logs\odoo_run_8069.log`
