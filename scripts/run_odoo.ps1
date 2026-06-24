#
# Jalankan Odoo dari terminal (TIDAK pakai service Windows).
#
# Pakai: dari PowerShell di D:\Unitrade\Unitrade-Oddo
#   .\run_odoo.ps1
#
# Stop: tekan Ctrl+C di terminal.
#
# Catatan:
# - Service `odoo-server-17.0` dimatikan dulu kalau jalan, supaya port 8069 bebas.
# - Stop service butuh admin: skrip ini akan minta UAC otomatis bila perlu.
# - Setelah service mati, Odoo dijalankan langsung di terminal sebagai user kamu.
#

$ErrorActionPreference = 'Stop'

$OdooHome = 'C:\Program Files\Odoo 17.0.20260217'
$OdooPy   = Join-Path $OdooHome 'python\python.exe'
$OdooBin  = Join-Path $OdooHome 'server\odoo-bin'
$OdooConf = Join-Path $OdooHome 'server\odoo.conf'
$DbName   = 'unitrade_db'

# --- Stop service (butuh admin) ---
$svc = Get-Service -Name 'odoo-server-17.0' -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq 'Running') {
    Write-Host '[INFO] Service odoo-server-17.0 sedang jalan, akan dihentikan...' -ForegroundColor Yellow
    try {
        Stop-Service -Name 'odoo-server-17.0' -Force -ErrorAction Stop
        Write-Host '[OK] Service dihentikan.' -ForegroundColor Green
    } catch {
        Write-Host '[ERROR] Tidak bisa stop service tanpa admin.' -ForegroundColor Red
        Write-Host '       Jalankan PowerShell as Administrator lalu ulangi, atau matikan service manual.' -ForegroundColor Red
        exit 1
    }
}

# --- Cek port 8069 belum dipakai ---
$port = (Get-NetTCPConnection -LocalPort 8069 -State Listen -ErrorAction SilentlyContinue)
if ($port) {
    Write-Host "[ERROR] Port 8069 masih dipakai oleh PID $($port.OwningProcess). Tutup dulu." -ForegroundColor Red
    exit 1
}

Write-Host ''
Write-Host '========================================================' -ForegroundColor Cyan
Write-Host '  Menjalankan Odoo di terminal...' -ForegroundColor Cyan
Write-Host '  URL  : http://localhost:8069' -ForegroundColor Cyan
Write-Host '  DB   : ' $DbName -ForegroundColor Cyan
Write-Host '  Stop : tekan Ctrl+C' -ForegroundColor Cyan
Write-Host '========================================================' -ForegroundColor Cyan
Write-Host ''

# --- Run Odoo ---
& $OdooPy $OdooBin -c $OdooConf -d $DbName --dev=xml
