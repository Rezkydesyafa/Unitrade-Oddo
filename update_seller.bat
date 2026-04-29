@echo off
echo ========================================================
echo Updating UniTrade Modules and Restarting Odoo
echo ========================================================

echo 1. Upgrading modules 'unitrade_seller' and 'unitrade_theme'...
"C:\Program Files\Odoo 17.0.20260217\python\python.exe" "C:\Program Files\Odoo 17.0.20260217\server\odoo-bin" -c "C:\Program Files\Odoo 17.0.20260217\server\odoo.conf" -d unitrade_db -u unitrade_seller,unitrade_theme --stop-after-init

echo 2. Requesting Administrator Privileges to restart service...
powershell -Command "Start-Process -FilePath 'powershell.exe' -ArgumentList '-Command', 'Restart-Service odoo-server-17.0 -Force' -Verb RunAs -Wait"

echo.
echo ========================================================
echo Update Complete! Odoo service has been restarted.
echo ========================================================
pause
