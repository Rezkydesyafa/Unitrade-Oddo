#
# Fix DB schema mismatch setelah pull unitrade_theme dari Github.
# Jalankan jika muncul error 'column res_users.x_xxx does not exist'.
#
# Skrip ini:
# 1. Stop service Odoo
# 2. Hapus __pycache__ dari semua modul UniTrade
# 3. Upgrade unitrade_theme + unitrade_admin sekaligus
# 4. Selesai (Odoo dijalankan manual via run_odoo.ps1)
#

$ErrorActionPreference = 'Stop'

# Self-elevate
$current = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($current)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host '[INFO] Membutuhkan hak admin. Meminta UAC...' -ForegroundColor Yellow
    Start-Process -FilePath 'powershell.exe' `
        -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',$PSCommandPath `
        -Verb RunAs
    exit
}

$OdooHome = 'C:\Program Files\Odoo 17.0.20260217'
$OdooPy   = Join-Path $OdooHome 'python\python.exe'
$OdooBin  = Join-Path $OdooHome 'server\odoo-bin'
$OdooConf = Join-Path $OdooHome 'server\odoo.conf'
$DbName   = 'unitrade_db'
$ProjectDir = 'D:\Unitrade\Unitrade-Oddo'

Write-Host ''
Write-Host '== Step 1: Stop service odoo-server-17.0 ==' -ForegroundColor Cyan
$svc = Get-Service -Name 'odoo-server-17.0' -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq 'Running') {
    Stop-Service -Name 'odoo-server-17.0' -Force
    Write-Host '[OK] Service dihentikan.' -ForegroundColor Green
} else {
    Write-Host '[skip] Service belum jalan.' -ForegroundColor DarkGray
}

Write-Host ''
Write-Host '== Step 2: Hapus __pycache__ semua modul UniTrade ==' -ForegroundColor Cyan
$modules = @(
    'unitrade_admin',
    'unitrade_theme',
    'unitrade_seller',
    'unitrade_product_ext',
    'unitrade_review',
    'unitrade_chat',
    'unitrade_delivery',
    'unitrade_payment',
    'unitrade_notification',
    'unitrade_wishlist'
)
foreach ($m in $modules) {
    $modPath = Join-Path $ProjectDir $m
    if (Test-Path $modPath) {
        Get-ChildItem $modPath -Recurse -Filter '__pycache__' -Directory -ErrorAction SilentlyContinue |
            ForEach-Object {
                Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
                Write-Host "  removed: $($_.FullName)" -ForegroundColor DarkGray
            }
    }
}

Write-Host ''
Write-Host '== Step 3: Upgrade unitrade_theme + unitrade_admin (sync schema) ==' -ForegroundColor Cyan
& $OdooPy $OdooBin -c $OdooConf -d $DbName --without-demo=all `
    -u unitrade_theme,unitrade_admin --stop-after-init --no-http
if ($LASTEXITCODE -ne 0) {
    Write-Host '[ERROR] Upgrade gagal. Cek logs/odoo.log.' -ForegroundColor Red
    Read-Host 'Enter untuk keluar'
    exit $LASTEXITCODE
}

Write-Host ''
Write-Host '[OK] Schema sudah disinkronkan.' -ForegroundColor Green
Write-Host '     Jalankan: .\run_odoo.ps1' -ForegroundColor Yellow
Write-Host ''
Read-Host 'Tekan Enter untuk menutup'
