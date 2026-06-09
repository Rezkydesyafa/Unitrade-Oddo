@echo off
REM ============================================================
REM  Upgrade modul unitrade_cs_ai (Customer Service AI).
REM
REM  PRA-SYARAT: Odoo TIDAK boleh sedang jalan di port 8069.
REM   - Jika pakai service Windows odoo-server-17.0, stop dulu:
REM       (PowerShell as Administrator)  net stop odoo-server-17.0
REM   - Jika pakai run_odoo.ps1, tekan Ctrl+C di terminalnya.
REM ============================================================

set "ODOO_HOME=C:\Program Files\Odoo 17.0.20260217"
set "ODOO_PY=%ODOO_HOME%\python\python.exe"
set "ODOO_BIN=%ODOO_HOME%\server\odoo-bin"
set "ODOO_CONF=%ODOO_HOME%\server\odoo.conf"
set "DB_NAME=unitrade_db"

netstat -ano | findstr ":8069 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo.
    echo [ERROR] Port 8069 masih dipakai. Stop dulu Odoo/service yang sedang jalan.
    echo         PowerShell as Administrator:  net stop odoo-server-17.0
    echo.
    pause
    exit /b 1
)

echo ========================================================
echo Upgrading unitrade_theme + unitrade_cs_ai ...
echo Database : %DB_NAME%
echo ========================================================

"%ODOO_PY%" "%ODOO_BIN%" -c "%ODOO_CONF%" -d %DB_NAME% --without-demo=all -u unitrade_theme,unitrade_cs_ai --stop-after-init --no-http
if errorlevel 1 (
    echo.
    echo [ERROR] Upgrade gagal. Cek logs\odoo.log baris terakhir.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo Upgrade selesai. Jalankan kembali Odoo:
echo   - service:  net start odoo-server-17.0   (atau .\run_odoo.ps1)
echo ========================================================
pause
