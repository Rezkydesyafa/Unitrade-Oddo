@echo off
REM ============================================================
REM  Upgrade seluruh modul UniTrade tanpa butuh hak admin.
REM
REM  PRA-SYARAT:
REM   1. Service Windows odoo-server-17.0 sudah di-disable
REM      (lihat one_time_setup.bat).
REM   2. WAJIB: Stop dulu Odoo yang sedang jalan!
REM      Kalau pakai run_odoo.ps1, tekan Ctrl+C di terminalnya,
REM      tunggu sampai prompt PS> kembali.
REM      Database dipakai eksklusif saat upgrade, jadi tidak boleh
REM      ada instance Odoo lain yang aktif di DB yang sama.
REM
REM  Pakai konfigurasi yang SAMA dengan run_odoo.ps1:
REM    C:\Program Files\Odoo 17.0.20260217\server\odoo.conf
REM ============================================================

set "ODOO_HOME=C:\Program Files\Odoo 17.0.20260217"
set "ODOO_PY=%ODOO_HOME%\python\python.exe"
set "ODOO_BIN=%ODOO_HOME%\server\odoo-bin"
set "ODOO_CONF=%ODOO_HOME%\server\odoo.conf"
set "DB_NAME=unitrade_db"

if not exist "%ODOO_PY%" (
    echo [ERROR] Tidak menemukan Python Odoo di "%ODOO_PY%".
    pause
    exit /b 1
)
if not exist "%ODOO_CONF%" (
    echo [ERROR] Tidak menemukan odoo.conf di "%ODOO_CONF%".
    pause
    exit /b 1
)

REM --- Cek port 8069 tidak terpakai (Odoo lain masih jalan) ---
netstat -ano | findstr ":8069 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo.
    echo [ERROR] Port 8069 masih dipakai. Stop dulu Odoo yang sedang jalan:
    echo         - Kalau pakai run_odoo.ps1, tekan Ctrl+C di terminalnya
    echo         - Tunggu sampai prompt PS^> kembali
    echo         - Baru jalankan upgrade_theme.bat lagi
    echo.
    pause
    exit /b 1
)

echo ========================================================
echo Upgrading semua modul UniTrade ...
echo Database : %DB_NAME%
echo Config   : %ODOO_CONF%
echo ========================================================

"%ODOO_PY%" "%ODOO_BIN%" -c "%ODOO_CONF%" -d %DB_NAME% --without-demo=all -u unitrade_theme,unitrade_product_ext,unitrade_seller,unitrade_review,unitrade_chat,unitrade_delivery,unitrade_payment,unitrade_dispute,unitrade_notification,unitrade_wishlist,unitrade_cs_ai,unitrade_admin --stop-after-init --no-http
if errorlevel 1 (
    echo.
    echo [ERROR] Upgrade gagal. Cek logs/odoo.log baris terakhir.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo Upgrade selesai.
echo Jalankan kembali Odoo:  .\run_odoo.ps1
echo ========================================================
pause
