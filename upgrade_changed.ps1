#
# Smart upgrade: stop Odoo, hapus pycache, upgrade SEMUA modul UniTrade.
# Aman dijalankan setelah `git pull` apapun yang berubah.
#
# - Tidak butuh admin kalau service sudah Disabled (mode dev).
# - Self-elevate kalau service masih aktif.
#

$ErrorActionPreference = 'Stop'

$OdooHome = 'C:\Program Files\Odoo 17.0.20260217'
$OdooPy   = Join-Path $OdooHome 'python\python.exe'
$OdooBin  = Join-Path $OdooHome 'server\odoo-bin'
$OdooConf = Join-Path $OdooHome 'server\odoo.conf'
$DbName   = 'unitrade_db'
$ProjectDir = 'D:\Unitrade\Unitrade-Oddo'

# Daftar semua modul UniTrade
$Modules = @(
    'unitrade_theme',
    'unitrade_seller',
    'unitrade_product_ext',
    'unitrade_review',
    'unitrade_chat',
    'unitrade_delivery',
    'unitrade_payment',
    'unitrade_notification',
    'unitrade_wishlist',
    'unitrade_admin'
)

# ---- Cek service status ----
$svc = Get-Service -Name 'odoo-server-17.0' -ErrorAction SilentlyContinue
$serviceWasRunning = $false
if ($svc -and $svc.Status -eq 'Running') {
    $serviceWasRunning = $true
    # Butuh admin untuk stop service
    $current = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($current)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Host '[INFO] Service Odoo aktif. Butuh admin untuk stop. Meminta UAC...' -ForegroundColor Yellow
        Start-Process -FilePath 'powershell.exe' `
            -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',$PSCommandPath `
            -Verb RunAs
        exit
    }
    Write-Host '[1/4] Stop service odoo-server-17.0...' -ForegroundColor Cyan
    Stop-Service -Name 'odoo-server-17.0' -Force
} else {
    Write-Host '[1/4] Service tidak aktif, lanjut tanpa admin.' -ForegroundColor Cyan
}

# ---- Cek port 8069 ----
$port = Get-NetTCPConnection -LocalPort 8069 -State Listen -ErrorAction SilentlyContinue
if ($port) {
    Write-Host "[ERROR] Port 8069 dipakai PID $($port.OwningProcess). Tutup terminal Odoo dulu." -ForegroundColor Red
    Read-Host 'Enter untuk keluar'
    exit 1
}

# ---- Hapus pycache ----
Write-Host '[2/4] Hapus __pycache__ semua modul UniTrade...' -ForegroundColor Cyan
foreach ($m in $Modules) {
    $modPath = Join-Path $ProjectDir $m
    if (Test-Path $modPath) {
        Get-ChildItem $modPath -Recurse -Filter '__pycache__' -Directory -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# ---- Upgrade semua modul ----
Write-Host '[3/4] Upgrade semua modul UniTrade (sync DB schema)...' -ForegroundColor Cyan
$moduleList = $Modules -join ','
& $OdooPy $OdooBin -c $OdooConf -d $DbName --without-demo=all `
    -u $moduleList --stop-after-init --no-http
if ($LASTEXITCODE -ne 0) {
    Write-Host '[ERROR] Upgrade gagal. Cek logs/odoo.log.' -ForegroundColor Red
    Read-Host 'Enter untuk keluar'
    exit $LASTEXITCODE
}

# ---- Start service kembali kalau tadinya running ----
if ($serviceWasRunning) {
    Write-Host '[4/4] Start service odoo-server-17.0...' -ForegroundColor Cyan
    Start-Service -Name 'odoo-server-17.0'
    Write-Host '[OK] Service running.' -ForegroundColor Green
    Write-Host '     Buka http://localhost:8069 (Ctrl+Shift+R untuk hard refresh)' -ForegroundColor Yellow
} else {
    Write-Host '[4/4] Mode dev: jalankan .\run_odoo.ps1 untuk start Odoo.' -ForegroundColor Yellow
}

Write-Host ''
Read-Host 'Tekan Enter untuk menutup'
