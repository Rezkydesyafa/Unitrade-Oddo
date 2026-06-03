#
# Install / upgrade module unitrade_admin dari terminal.
#
# - Stop service Odoo (butuh admin)
# - Hapus __pycache__ unitrade_admin agar Python pasti reload modul
# - Upgrade unitrade_admin
#
# Pakai: dari PowerShell (Run as Administrator) di D:\Unitrade\Unitrade-Oddo
#   .\install_admin.ps1
#
# Setelah selesai, jalankan: .\run_odoo.ps1
#

$ErrorActionPreference = 'Stop'

# Self-elevate kalau belum admin
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
Write-Host '== Step 2: Hapus __pycache__ unitrade_admin ==' -ForegroundColor Cyan
Get-ChildItem -Path "$ProjectDir\unitrade_admin" -Recurse -Filter '__pycache__' -Directory -ErrorAction SilentlyContinue |
    ForEach-Object {
        Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  removed: $($_.FullName)" -ForegroundColor DarkGray
    }

Write-Host ''
Write-Host '== Step 3: Install / Upgrade unitrade_admin ==' -ForegroundColor Cyan
& $OdooPy $OdooBin -c $OdooConf -d $DbName --without-demo=all `
    -i unitrade_admin -u unitrade_admin --stop-after-init --no-http
if ($LASTEXITCODE -ne 0) {
    Write-Host '[ERROR] Install gagal. Cek logs/odoo.log.' -ForegroundColor Red
    Read-Host 'Enter untuk keluar'
    exit $LASTEXITCODE
}

Write-Host ''
Write-Host '[OK] Install/Upgrade selesai.' -ForegroundColor Green
Write-Host '     Jalankan: .\run_odoo.ps1' -ForegroundColor Yellow
Write-Host ''
Read-Host 'Tekan Enter untuk menutup'
