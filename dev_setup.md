# UniTrade — Dev Setup & Workflow

## Prasyarat (sekali)

- Odoo 17 sudah terinstal di `C:\Program Files\Odoo 17.0.20260217\`
- PostgreSQL bawaan Odoo sudah berjalan
- Database `unitrade_db` sudah ada
- Folder data sudah dipindah ke lokasi user-writable: `D:\Unitrade\Odoo-Data` (lihat `odoo.conf` baris `data_dir`)

## Mode Development (RECOMMENDED — tidak butuh admin)

Jalankan Odoo dari terminal, service Windows di-set Disabled:

```powershell
# Sekali saja: disable service supaya tidak konflik
sc.exe config odoo-server-17.0 start=disabled
sc.exe stop   odoo-server-17.0
```

Setelah itu, kamu (dan setiap anggota tim) cukup pakai:

```powershell
.\run_odoo.ps1
```

Tutup dengan `Ctrl+C`. Restart dengan menjalankan ulang.

## Saat git pull dari Github

Tergantung apa yang berubah:

| Yang di-pull | Apa yang harus dilakukan |
|---|---|
| Cuma XML view | Refresh browser (`Ctrl+Shift+R`) |
| Cuma SCSS/JS | Stop Odoo (Ctrl+C) → `.\run_odoo.ps1` |
| Model Python (field/method baru) | Stop Odoo → `.\upgrade_changed.ps1` → `.\run_odoo.ps1` |

Kalau ragu, **selalu upgrade**. Itu selalu aman.

## Mode Production (service)

Kalau mau Odoo selalu jalan otomatis:

```powershell
# Run as Administrator
sc.exe config odoo-server-17.0 start=auto
net start odoo-server-17.0
```

Saat ada update model dari Github, **wajib admin**:

```powershell
.\upgrade_theme.bat   # Run as Administrator
```

## Troubleshooting

### "column res_users.x_xxx does not exist"
Anggota tim lain menambah field di model tapi kamu belum upgrade module-nya.
Solusi: jalankan `upgrade_changed.ps1`.

### Asset frontend (CSS) tidak ter-update
Browser cache lama. Tekan `Ctrl+Shift+R` untuk hard refresh.

### Port 8069 sudah dipakai
Service masih running. Stop dulu: `net stop odoo-server-17.0` (admin) atau pakai script.
