$env:PGPASSWORD = 'admin'
$psql = 'C:\Program Files\Odoo 17.0.20260217\PostgreSQL\bin\psql.exe'
$sql = "SELECT name, state FROM ir_module_module WHERE name LIKE 'unitrade_%' ORDER BY name;"
& $psql -h localhost -U openpg -d unitrade_db -c $sql
