@echo off
REM ============================================================
REM  UniTrade fix script
REM  Tujuan:
REM    1. Stop service Odoo
REM    2. Pindahkan data_dir ke folder user-writable (D:\Unitrade\Odoo-Data)
REM    3. Copy filestore lama supaya attachment lama tetap ada
REM    4. Update odoo.conf milik service (di Program Files) agar pakai data_dir baru
REM    5. Reset demo flag dan state modul yang corrupt di DB
REM    6. Pasang/Upgrade modul base + UniTrade
REM    7. Start service kembali
REM
REM  Auto-elevate jika belum admin.
REM ============================================================

REM ---- self-elevation ----
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Membutuhkan hak admin. Meminta UAC...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

setlocal EnableExtensions EnableDelayedExpansion

set "ODOO_HOME=C:\Program Files\Odoo 17.0.20260217"
set "ODOO_PY=%ODOO_HOME%\python\python.exe"
set "ODOO_BIN=%ODOO_HOME%\server\odoo-bin"
set "ODOO_CONF_SVC=%ODOO_HOME%\server\odoo.conf"
set "PSQL=%ODOO_HOME%\PostgreSQL\bin\psql.exe"
set "OLD_FILESTORE=%ODOO_HOME%\sessions\filestore"
set "NEW_DATA=D:\Unitrade\Odoo-Data"
set "NEW_FILESTORE=%NEW_DATA%\filestore"
set "NEW_SESSIONS=%NEW_DATA%\sessions"
set "DB_NAME=unitrade_db"
set "DB_USER=openpg"
set "DB_PASS=admin"

echo.
echo === Step 1: Stop service odoo-server-17.0 (kalau jalan) ===
sc query odoo-server-17.0 >nul 2>&1
if %errorlevel%==0 (
    net stop odoo-server-17.0
) else (
    echo    [skip] service belum ada / sudah berhenti.
)

echo.
echo === Step 2: Buat folder data baru yang user-writable ===
if not exist "%NEW_DATA%" mkdir "%NEW_DATA%"
if not exist "%NEW_FILESTORE%" mkdir "%NEW_FILESTORE%"
if not exist "%NEW_SESSIONS%" mkdir "%NEW_SESSIONS%"

echo.
echo === Step 3: Copy filestore lama (kalau ada) ===
if exist "%OLD_FILESTORE%\%DB_NAME%" (
    echo    Menyalin filestore lama ke %NEW_FILESTORE%\%DB_NAME% ...
    if not exist "%NEW_FILESTORE%\%DB_NAME%" mkdir "%NEW_FILESTORE%\%DB_NAME%"
    robocopy "%OLD_FILESTORE%\%DB_NAME%" "%NEW_FILESTORE%\%DB_NAME%" /E /COPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS /NP
) else (
    echo    [skip] tidak ada filestore lama untuk %DB_NAME%
)

echo.
echo === Step 4: Update data_dir di odoo.conf service ===
powershell -NoProfile -Command "$f='%ODOO_CONF_SVC%'; $c=Get-Content -LiteralPath $f -Raw; $c=$c -replace '(?m)^\s*data_dir\s*=.*$','data_dir = %NEW_DATA:\=\\%'; Set-Content -LiteralPath $f -Value $c -NoNewline -Encoding ASCII"
if errorlevel 1 (
    echo    [WARN] gagal update odoo.conf service. Edit manual: data_dir = %NEW_DATA%
) else (
    echo    OK: %ODOO_CONF_SVC% sekarang pakai data_dir = %NEW_DATA%
)

echo.
echo === Step 5: Reset DB state (demo flag + modul corrupt) ===
set "PGPASSWORD=%DB_PASS%"
"%PSQL%" -h localhost -U %DB_USER% -d %DB_NAME% -v ON_ERROR_STOP=1 -c "UPDATE ir_module_module SET demo=false WHERE demo=true;"
"%PSQL%" -h localhost -U %DB_USER% -d %DB_NAME% -v ON_ERROR_STOP=1 -c "UPDATE ir_module_module SET state='uninstalled' WHERE state IN ('to install','to upgrade','to remove') AND name LIKE 'unitrade_%%';"
"%PSQL%" -h localhost -U %DB_USER% -d %DB_NAME% -v ON_ERROR_STOP=1 -c "UPDATE ir_module_module SET state='uninstalled' WHERE state IN ('to install','to upgrade','to remove') AND name='website_sale_stock';"
set "PGPASSWORD="

echo.
echo === Step 6: Install/Upgrade modul UniTrade (no demo, no http) ===
"%ODOO_PY%" "%ODOO_BIN%" -c "%ODOO_CONF_SVC%" -d %DB_NAME% --without-demo=all -i website_sale_stock,unitrade_theme,unitrade_seller,unitrade_product_ext,unitrade_review,unitrade_chat,unitrade_delivery,unitrade_payment,unitrade_notification,unitrade_wishlist,unitrade_admin -u base --stop-after-init --no-http
if errorlevel 1 (
    echo.
    echo  [ERROR] Install gagal. Cek %CD%\logs\odoo.log untuk detail.
    pause
    exit /b 1
)

echo.
echo === Step 7: Start service Odoo ===
net start odoo-server-17.0
if errorlevel 1 (
    echo    [WARN] gagal start service. Coba manual: net start odoo-server-17.0
)

echo.
echo ============================================================
echo  Selesai. Buka http://localhost:8069/odoo dan coba login.
echo  Filestore baru ada di %NEW_FILESTORE%
echo ============================================================
pause
endlocal
