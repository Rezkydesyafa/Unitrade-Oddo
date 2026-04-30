@echo off
:: ===================================================
:: Auto-elevate to Administrator
:: ===================================================
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Meminta akses Administrator...
    powershell -Command "Start-Process cmd -ArgumentList '/c \"%~f0\"' -Verb RunAs"
    exit /b
)

echo.
echo ===================================================
echo  Install PaddleOCR ke Odoo Python [ADMINISTRATOR]
echo ===================================================
echo.

echo [1/4] Menghentikan Odoo service...
net stop odoo-server-17.0 2>nul
timeout /t 5 /nobreak >nul
echo      Done.
echo.

echo [2/4] Menginstall paddleocr ke Odoo Python...
echo      Lokasi: C:\Program Files\Odoo 17.0.20260217\python
echo      Mohon tunggu, ini bisa 2-5 menit...
echo.
"C:\Program Files\Odoo 17.0.20260217\python\python.exe" -m pip install paddleocr paddlepaddle Pillow numpy --no-user --force-reinstall 2>&1
echo.

echo [3/4] Verifikasi instalasi...
"C:\Program Files\Odoo 17.0.20260217\python\python.exe" -c "import paddleocr; print('paddleocr OK:', paddleocr.__version__)" 2>nul
if %errorlevel% equ 0 (
    echo      [SUKSES] paddleocr terinstall!
) else (
    echo      [GAGAL] paddleocr tidak ditemukan.
)
echo.

echo [4/4] Memulai ulang Odoo service...
net start odoo-server-17.0 2>nul
echo.

echo ===================================================
echo  SELESAI! Silakan test verifikasi KTM di browser.
echo ===================================================
echo.
pause
