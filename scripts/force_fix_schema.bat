@echo off
REM ============================================================
REM  FORCE upgrade unitrade_theme dan registry refresh.
REM  Klik kanan -> Run as administrator
REM ============================================================

REM Self-elevate
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
echo Step 1: STOP service
echo ========================================================
net stop odoo-server-17.0
timeout /t 2 /nobreak >nul

echo.
echo ========================================================
echo Step 2: Hapus pycache modul UniTrade
echo ========================================================
for /d /r "D:\Unitrade\Unitrade-Oddo" %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
echo Done.

echo.
echo ========================================================
echo Step 3: Hapus REGISTRY signaling cache (paksa rebuild)
echo Ini akan membuat Odoo membaca ulang semua model dari Python
echo ========================================================
del /q "D:\Unitrade\Odoo-Data\sessions\*.*" 2>nul
echo Done.

echo.
echo ========================================================
echo Step 4: FORCE upgrade unitrade_theme dan modul UniTrade
echo (dengan --update sehingga _auto_init dijamin jalan)
echo ========================================================
"%ODOO_PY%" "%ODOO_BIN%" -c "%ODOO_CONF%" -d %DB_NAME% --without-demo=all --update unitrade_theme,unitrade_seller,unitrade_chat,unitrade_admin --stop-after-init --no-http
if errorlevel 1 (
    echo.
    echo  [ERROR] Upgrade gagal. Cek logs/odoo.log.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo Step 5: START service kembali
echo ========================================================
net start odoo-server-17.0

echo.
echo ========================================================
echo SELESAI.
echo  - Buka http://localhost:8069
echo  - Hard refresh dengan Ctrl+Shift+R
echo ========================================================
pause
