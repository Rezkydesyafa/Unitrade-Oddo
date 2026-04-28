import psycopg2
conn = psycopg2.connect(dbname='unitrade_db', user='openpg', password='admin')
cur = conn.cursor()
cur.execute("SELECT id, name, key FROM ir_ui_view WHERE key LIKE '%unitrade_product%' OR name LIKE '%UniTrade Product Detail%';")
res = cur.fetchall()
for r in res:
    print("ID:", r[0], "Name:", r[1], "Key:", r[2])
if not res:
    print("No views found matching unitrade_product")
