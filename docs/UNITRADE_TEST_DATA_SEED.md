# UniTrade Test Data Seed

Script: `scripts/seed_unitrade_test_data.py`

Tujuan:
- Membersihkan produk marketplace UniTrade dan data transaksi terkait yang mengunci produk.
- Membuat ulang data testing fresh untuk buyer, seller, produk, order, refund, chat, tiket customer service, dan review.
- Setiap produk seed memiliki minimal 5 review rating 5.
- Melengkapi data dengan gambar produk, gallery produk, foto profil user, foto KTM seller, bukti refund, bukti serah/terima barang.

Default script adalah dry-run. Tidak ada data yang dihapus atau dibuat sebelum environment variable `UNITRADE_RESET_TEST_DATA=YES` di-set.

## Via Task Runner Windows

Dry-run:

```powershell
.\scripts\unitrade.ps1 seed-dry
```

Execute reset + seed:

```powershell
.\scripts\unitrade.ps1 seed
```

## Dry-run

```powershell
Get-Content 'D:\Unitrade_Oddo\scripts\seed_unitrade_test_data.py' | & 'C:\Program Files\Odoo 17.0.20260217\python\python.exe' 'C:\Program Files\Odoo 17.0.20260217\server\odoo-bin' shell -c 'C:\Program Files\Odoo 17.0.20260217\server\odoo.conf' -d unitrade_db --no-http --data-dir='D:\Unitrade_Oddo\odoo_data' --logfile='D:\Unitrade_Oddo\logs\seed_unitrade_test_data_dry_run.log'
```

## Execute

```powershell
$env:UNITRADE_RESET_TEST_DATA='YES'
Get-Content 'D:\Unitrade_Oddo\scripts\seed_unitrade_test_data.py' | & 'C:\Program Files\Odoo 17.0.20260217\python\python.exe' 'C:\Program Files\Odoo 17.0.20260217\server\odoo-bin' shell -c 'C:\Program Files\Odoo 17.0.20260217\server\odoo.conf' -d unitrade_db --no-http --data-dir='D:\Unitrade_Oddo\odoo_data' --logfile='D:\Unitrade_Oddo\logs\seed_unitrade_test_data_execute.log'
Remove-Item Env:\UNITRADE_RESET_TEST_DATA
```

## Akun Testing

Password default semua akun: `UnitradeTest123!`

Buyer:
- `unitrade.test.buyer.fuad@unitrade.test`
- `unitrade.test.buyer.maharani@unitrade.test`
- `unitrade.test.buyer.salsa@unitrade.test`
- `unitrade.test.buyer.andika@unitrade.test`

Seller:
- `unitrade.test.seller.nurpia@unitrade.test`
- `unitrade.test.seller.dwi@unitrade.test`
- `unitrade.test.seller.rizky@unitrade.test`

## Catatan Cleanup

Script menghapus produk dengan `x_is_marketplace=True` atau kode `UT-SEED-*`, beserta order, refund, chat, review, escrow ledger, payment intent, dan tiket seed yang terkait.

Produk sistem seperti biaya layanan/payment fee tidak ikut dihapus. Jika ada produk yang tidak bisa dihapus karena masih dikunci foreign key Odoo, script akan menonaktifkan produk tersebut sebagai fallback.

Script memakai attachment storage database sementara saat execute agar gambar seed tidak gagal karena permission filestore Windows. Setelah selesai, konfigurasi `ir_attachment.location` dikembalikan ke kondisi sebelumnya.
