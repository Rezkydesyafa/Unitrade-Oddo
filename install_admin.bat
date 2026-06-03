@echo off
REM ============================================================
REM  Install / Upgrade modul UniTrade Admin Dashboard
REM  Auto-elevate jika belum admin.
REM ============================================================

REM ---- self-elevation ----
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
echo Stopping odoo-server-17.0 ...
echo ========================================================
net stop odoo-server-17.0 2>nul

echo.
echo ========================================================
echo Installing/Upgrading unitrade_admin ...
echo ========================================================
"%ODOO_PY%" "%ODOO_BIN%" -c "%ODOO_CONF%" -d %DB_NAME% --without-demo=all -i unitrade_admin -u unitrade_seller --stop-after-init --no-http
if errorlevel 1 (
    echo.
    echo  [ERROR] Install gagal. Cek logs/odoo.log.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo Starting odoo-server-17.0 ...
echo ========================================================
net start odoo-server-17.0

echo.
echo ========================================================
echo Selesai. Buka http://localhost:8069/odoo
echo  - Login dengan akun admin / Super Admin UniTrade
echo  - Menu kiri: UniTrade -^> Dashboard Admin
echo ========================================================
pause
