@echo off
echo ===================================================
echo Meng-upgrade modul unitrade_theme dan unitrade_product_ext...
echo Mohon tunggu sebentar.
echo ===================================================

"C:\Program Files\Odoo 17.0.20260217\python\python.exe" "C:\Program Files\Odoo 17.0.20260217\server\odoo-bin" -c "C:\Program Files\Odoo 17.0.20260217\server\odoo.conf" -d unitrade_db -u unitrade_theme,unitrade_product_ext,unitrade_seller --stop-after-init

echo.
echo ===================================================
echo Upgrade selesai!
echo ===================================================
pause
