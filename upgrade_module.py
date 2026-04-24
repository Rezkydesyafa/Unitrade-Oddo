"""Script to upgrade unitrade_product_ext module in Odoo."""
import subprocess
import sys
import time

ODOO_BIN = r"C:\Program Files\Odoo 17.0.20260217\server\odoo-bin"
ODOO_CONF = r"C:\Program Files\Odoo 17.0.20260217\server\odoo.conf"
DB_NAME = "unitrade_db"
MODULE = "unitrade_product_ext"

print("=== UniTrade Module Upgrade Script ===")

# Step 1: Stop the service
print("\n[1] Stopping Odoo service...")
result = subprocess.run(["net", "stop", "odoo-server-17.0"], capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print(f"Warning: {result.stderr}")
time.sleep(3)

# Step 2: Run upgrade
print(f"\n[2] Upgrading module '{MODULE}'...")
result = subprocess.run(
    [sys.executable, ODOO_BIN, "-c", ODOO_CONF, "-u", MODULE, "-d", DB_NAME, "--stop-after-init"],
    capture_output=True, text=True, timeout=120
)
print("STDOUT:", result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
    print(f"\n!!! Upgrade failed with exit code {result.returncode}")
else:
    print("\n[OK] Module upgraded successfully!")

time.sleep(2)

# Step 3: Start the service
print("\n[3] Starting Odoo service...")
result = subprocess.run(["net", "start", "odoo-server-17.0"], capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print(f"Warning: {result.stderr}")

print("\n=== Done ===")
