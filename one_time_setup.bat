@echo off
REM ============================================================
REM  ONE-TIME SETUP untuk UniTrade Dev Mode
REM
REM  Setelah skrip ini selesai:
REM    - Service Odoo Windows diset Disabled (tidak auto-start)
REM    - Semua modul UniTrade ter-upgrade (kolom DB sinkron)
REM    - Schema res_users dipastikan benar (x_terms_privacy_accepted dll)
REM
REM  Selanjutnya: pakai .\run_odoo.ps1 untuk jalankan Odoo (tidak butuh admin)
REM
REM  Jalankan: klik kanan -> Run as administrator
REM ============================================================

REM ---- self-elevate ----
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Membutuhkan hak admin. Meminta UAC...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

set "ODOO_HOME=C:\Program Files\Odoo 17.0.20260217"
set "ODOO_PY=%ODOO_HOME%\python\python.exe"
set "ODOO_BIN=%ODOO_HOME%\server\odoo-bin"
set "ODOO_CONF=%ODOO_HOME%\server\odoo.conf"
set "DB_NAME=unitrade_db"

echo ========================================================
echo Step 1/5: Stop service odoo-server-17.0
echo ========================================================
net stop odoo-server-17.0 2>nul
timeout /t 2 /nobreak >nul

echo.
echo ========================================================
echo Step 2/5: Set service ke Disabled (mode dev)
echo ========================================================
sc.exe config odoo-server-17.0 start= disabled
echo Service sekarang Disabled. Tidak akan auto-start saat boot.

echo.
echo ========================================================
echo Step 3/5: Hapus pycache modul UniTrade
echo ========================================================
for /d /r "D:\Unitrade\Unitrade-Oddo" %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
echo Done.

echo.
echo ========================================================
echo Step 4/5: Upgrade SEMUA modul UniTrade (sync DB schema)
echo Ini akan menambah kolom-kolom yang missing di res_users.
echo ========================================================
"%ODOO_PY%" "%ODOO_BIN%" -c "%ODOO_CONF%" -d %DB_NAME% --without-demo=all -u unitrade_theme,unitrade_seller,unitrade_chat,unitrade_product_ext,unitrade_review,unitrade_delivery,unitrade_payment,unitrade_notification,unitrade_wishlist,unitrade_admin --stop-after-init --no-http
if errorlevel 1 (
    echo.
    echo  [ERROR] Upgrade gagal. Cek logs/odoo.log.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo Step 5/5: Selesai
echo ========================================================
echo.
echo  - Service: Disabled (tidak akan auto-start)
echo  - Schema DB: tersinkron dengan model Python terbaru
echo.
echo  Selanjutnya:
echo    - Jalankan Odoo: .\run_odoo.ps1 (TIDAK butuh admin)
echo    - Stop Odoo:     Ctrl+C di terminal
echo    - Setelah git pull yang ubah model: .\upgrade_changed.ps1
echo.
pause
