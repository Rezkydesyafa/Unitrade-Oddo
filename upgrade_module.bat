@echo off
echo === Stopping Odoo Service ===
net stop odoo-server-17.0
timeout /t 5 /nobreak

echo === Upgrading unitrade_product_ext module ===
"C:\Program Files\Odoo 17.0.20260217\python\python.exe" "C:\Program Files\Odoo 17.0.20260217\server\odoo-bin" -c "C:\Program Files\Odoo 17.0.20260217\server\odoo.conf" -u unitrade_product_ext -d unitrade_db --stop-after-init --logfile=D:\Unitrade_Oddo\logs\upgrade_result.log

echo Exit code: %errorlevel%
timeout /t 3 /nobreak

echo === Starting Odoo Service ===
net start odoo-server-17.0

echo === Done ===
